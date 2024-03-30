#!/bin/bash

for s in 0; do
    for ut in 0.01 0.025 0.05 0.075 0.1 0.25 0.5 0.75 1; do

  ##############################
  # UNCERTAINTY QUANTIFICATION # 
  ##############################
  # Intervention with point critic (sparse cost)
  # ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/critic_no_smoothing.yaml -s $s \
  #   --exp_name point_critic_intv_sparse_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

  # # Intervention with point critic (shaped cost)
  # ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/critic_smoothing.yaml -s $s \
  #   --exp_name point_critic_intv_shaped_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

  # Intervention with true model and sparse cost
  ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/sparse.yaml \
    -s $s --exp_name point_intv_true_model_sparse_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

  # Intervention with biased model and sparse cost
  ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/sparse.yaml \
    --model_config model/small.yaml -s $s --exp_name point_intv_biased_model_sparse_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

  # Intervention with true model and shaped cost
  ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/shaped.yaml \
    -s $s --exp_name point_intv_true_model_shaped_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

  # Intervention with biased model and shaped cost
  ./cppo.py --epochs 500 --ignore_unsafe_cost --intv_config intv/shaped.yaml \
    --model_config model/small.yaml -s $s --exp_name point_intv_biased_model_shaped_cost_UNCERTAINTY_${ut} --uncertainty --uncert_threshold $ut

    done
done 
