import numpy as np
import scipy.signal
from gym.spaces import Box, Discrete

import torch
import torch.nn as nn
from torch.distributions.normal import Normal
from torch.distributions.categorical import Categorical


def combined_shape(length, shape=None):
    if shape is None:
        return (length,)
    return (length, shape) if np.isscalar(shape) else (length, *shape)


def mlp(sizes, activation, output_activation=nn.Identity):
    layers = []
    for j in range(len(sizes)-1):
        act = activation if j < len(sizes)-2 else output_activation
        layers += [nn.Linear(sizes[j], sizes[j+1]), act()]
    return nn.Sequential(*layers) 


class mlpPriorEnsemble(nn.Module):
    
    def __init__(self, sizes, activation, output_activation=nn.Identity, num_heads = 7):
        super().__init__() 
        layers = []
        self.training_mode = True
        for j in range(len(sizes)-2):
            act = activation if j < len(sizes)-2 else output_activation
            layers += [nn.Linear(sizes[j], sizes[j+1]), act()]
        self.body = nn.Sequential(*layers)
        self.prior_body = nn.Sequential(*layers)
        self.output_heads = [nn.Linear(sizes[-2], sizes[-1], output_activation()) for _ in range(num_heads)]
        self.prior_output_heads = [nn.Linear(sizes[-2], sizes[-1], output_activation()) for _ in range(num_heads)]
        
    def forward(self, obs):
        raise NotImplementedError


        

def count_vars(module):
    return sum([np.prod(p.shape) for p in module.parameters()])


def discount_cumsum(x, discount):
    """
    magic from rllab for computing discounted cumulative sums of vectors.

    input:
        vector x,
        [x0,
         x1,
         x2]

    output:
        [x0 + discount * x1 + discount^2 * x2,
         x1 + discount * x2,
         x2]
    """
    return scipy.signal.lfilter([1], [1, float(-discount)], x[::-1], axis=0)[::-1]


class Actor(nn.Module):

    def _distribution(self, obs):
        raise NotImplementedError

    def _log_prob_from_distribution(self, pi, act):
        raise NotImplementedError

    def forward(self, obs, act=None):
        # Produce action distributions for given observations, and
        # optionally compute the log likelihood of given actions under
        # those distributions.
        pi = self._distribution(obs)
        logp_a = None
        if act is not None:
            logp_a = self._log_prob_from_distribution(pi, act)
        return pi, logp_a


class MLPCategoricalActor(Actor):

    def __init__(self, obs_dim, act_dim, hidden_sizes, activation):
        super().__init__()
        self.logits_net = mlp([obs_dim] + list(hidden_sizes) + [act_dim], activation)

    def _distribution(self, obs):
        logits = self.logits_net(obs)
        return Categorical(logits=logits)

    def _log_prob_from_distribution(self, pi, act):
        return pi.log_prob(act)


class MLPGaussianActor(Actor):

    def __init__(self, obs_dim, act_dim, hidden_sizes, activation, pred_std=False):
        super().__init__()
        self.act_dim = act_dim
        self.pred_std = pred_std
        if pred_std:
            self.pi_net = mlp([obs_dim] + list(hidden_sizes) + [2*act_dim], activation)
        else:
            log_std = -0.5 * np.ones(act_dim, dtype=np.float32)
            self.log_std = torch.nn.Parameter(torch.as_tensor(log_std))
            self.mu_net = mlp([obs_dim] + list(hidden_sizes) + [act_dim], activation)

    def _distribution(self, obs):
        if self.pred_std:
            pred = self.pi_net(obs)
            mu, log_std = pred[..., :self.act_dim], pred[..., self.act_dim:]
            std = torch.exp(log_std)
        else:
            mu = self.mu_net(obs)
            std = torch.exp(self.log_std)
        return Normal(mu, std)

    def _log_prob_from_distribution(self, pi, act):
        return pi.log_prob(act).sum(axis=-1)    # Last axis sum needed for Torch Normal distribution

    def mean_act(self, obs):
        if self.pred_std:
            return self.pi_net(obs)[..., :self.act_dim]
        return self.mu_net(obs)


class MLPCritic(nn.Module):

    def __init__(self, obs_dim, hidden_sizes, activation,
                 rnge=(float('-inf'), float('inf'))):
        super().__init__()
        self.v_net = mlp([obs_dim] + list(hidden_sizes) + [1], activation)
        self.rnge = rnge

    def forward(self, obs):
        return torch.squeeze(self.v_net(obs), -1) # Critical to ensure v has right shape.

class MLPCriticUncertainty(nn.Module):
    
    def __init__(self, obs_dim, hidden_sizes, activation,  
                 rnge=(float('-inf'), float('inf')), num_heads=7):
        super().__init__()
        self.v_net = mlpPriorEnsemble([obs_dim] + list(hidden_sizes) + [1], activation, num_heads=num_heads)
        self.rnge = rnge
        self.num_heads = num_heads
        self.active_heads = None
        
    def set_active_heads(self, active_heads:list):
        # set the active heads for gradient descent
        self.active_heads = active_heads
        

    def forward(self, obs):
        # Generate forward pass in prior network
        with torch.no_grad():
            prior_x = self.v_net.prior_body(obs)
            if self.active_heads != None:
                prior_out = torch.stack([self.v_net.prior_output_heads[i](prior_x) for i in self.active_heads])
                
            else:
                prior_out = torch.stack([head(prior_x) for head in self.v_net.prior_output_heads])
        # Generate forward pass with network
        x = self.v_net.body(obs)
        if self.active_heads != None:
            out = torch.stack([self.v_net.output_heads[i](x) for i in self.active_heads])
        else:
            out = torch.stack([head(x) for head in self.v_net.output_heads])
        # Add in priors to network outputs
        out_with_prior = torch.add(out, prior_out) # check this does the element wise-sum, especially in batchces
        mu_values = torch.mean(out_with_prior, dim=0)
        sigma_values = torch.var(out_with_prior, dim=0)
        # return the point estimates
        return torch.squeeze(mu_values, -1) # Critical to ensure v has right shape.
    
    def get_uncertainty(self, obs):
         # Generate forward pass in prior network
        with torch.no_grad():
            prior_x = self.v_net.prior_body(obs)
            if self.active_heads != None:
                prior_out = torch.stack([self.v_net.prior_output_heads[i](prior_x) for i in self.active_heads])
                
            else:
                prior_out = torch.stack([head(prior_x) for head in self.v_net.prior_output_heads])
        # Generate forward pass with network
        x = self.v_net.body(obs)
        if self.active_heads != None:
            out = torch.stack([self.v_net.output_heads[i](x) for i in self.active_heads])
        else:
            out = torch.stack([head(x) for head in self.v_net.output_heads])
        # Add in priors to network outputs
        out_with_prior = torch.add(out, prior_out) # check this does the element wise-sum, especially in batchces
        mu_values = torch.mean(out_with_prior, dim=0)
        sigma_values = torch.var(out_with_prior, dim=0)
        # return the point estimates
        return torch.squeeze (mu_values, -1), torch.squeeze(sigma_values, -1) # Critical to ensure v has right shape.
        

class MLPActorCritic(nn.Module):


    def __init__(self, observation_space, action_space,
                 hidden_sizes=(64,64), activation=nn.Tanh,
                 v_range=(float('-inf'), float('inf')),
                 vc_range=(float('-inf'), float('inf')),
                 pred_std=False):
        super().__init__()

        obs_dim = observation_space.shape[0]

        # policy builder depends on action space
        if isinstance(action_space, Box):
            self.pi = MLPGaussianActor(obs_dim, action_space.shape[0], hidden_sizes,
                                       activation, pred_std=pred_std)
        elif isinstance(action_space, Discrete):
            self.pi = MLPCategoricalActor(obs_dim, action_space.n, hidden_sizes, activation)

        # build value function
        self.v  = MLPCritic(obs_dim, hidden_sizes, activation, v_range)
        self.vc = MLPCritic(obs_dim, hidden_sizes, activation, vc_range)

    def step(self, obs):
        with torch.no_grad():
            pi = self.pi._distribution(obs)
            a = pi.sample()
            logp_a = self.pi._log_prob_from_distribution(pi, a)
            v = torch.clamp(self.v(obs), *self.v.rnge)
            vc = torch.clamp(self.vc(obs), *self.vc.rnge)
        return a.numpy(), v.numpy(), vc.numpy(), logp_a.numpy()

    def act(self, obs, deterministic=False):
        if deterministic:
            with torch.no_grad():
                return self.pi.mean_act(obs).numpy()
        return self.step(obs)[0]
    
    def get_uncertainty(self, obs):
        """Placeholder function"""
        return None, None



class MLPActorCriticUncertainty(nn.Module):


    def __init__(self, observation_space, action_space,
                 hidden_sizes=(64,64), activation=nn.Tanh,
                 v_range=(float('-inf'), float('inf')),
                 vc_range=(float('-inf'), float('inf')),
                 pred_std=False, num_heads = 7):
        super().__init__()

        obs_dim = observation_space.shape[0]

        # policy builder depends on action space
        if isinstance(action_space, Box):
            self.pi = MLPGaussianActor(obs_dim, action_space.shape[0], hidden_sizes,
                                       activation, pred_std=pred_std)
        elif isinstance(action_space, Discrete):
            self.pi = MLPCategoricalActor(obs_dim, action_space.n, hidden_sizes, activation)

        # build value function
        self.v  = MLPCriticUncertainty(obs_dim, hidden_sizes, activation, v_range, num_heads=7)
        self.vc = MLPCritic(obs_dim, hidden_sizes, activation, vc_range)

    def step(self, obs):
        with torch.no_grad():
            pi = self.pi._distribution(obs)
            a = pi.sample()
            logp_a = self.pi._log_prob_from_distribution(pi, a)
            # alter steps to only take first value from step_function
            v_output_mu = self.v(obs)
            v = torch.clamp(v_output_mu, *self.v.rnge)
            vc = torch.clamp(self.vc(obs), *self.vc.rnge)
        return a.numpy(), v.numpy(), vc.numpy(), logp_a.numpy()

    def act(self, obs, deterministic=False):
        if deterministic:
            with torch.no_grad():
                return self.pi.mean_act(obs).numpy()
        return self.step(obs)[0]

    def get_uncertainty(self, obs):
        """Get the uncertainty estimate over all uncertain heads"""
        self.v.active_heads=None
        mu, sigma = self.v.get_uncertainty(obs)
        return mu, sigma