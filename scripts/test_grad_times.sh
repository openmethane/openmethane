#!/bin/bash
# skeleton in response to the following kagi prompt:
# write a doubly nested loop in bash where the outer loop in the variable ipert goes from 0 to 24 and the inner loop veriable imeas goes from ipert+1 to 24

for ipert in {0..24}
do
  for imeas in $(seq $((ipert + 1)) 24)
  do
    TEST_GRAD_MEASURE_TIME=$imeas TEST_GRAD_PERT_TIME=$ipert bash scripts/docker-e2e-monthly.sh |& tail -10
  done
done
