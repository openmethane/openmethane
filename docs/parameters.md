# Parameters

The following environment variables are configurable:

| Variable         | Type              | Description                           | Default     |
|------------------|-------------------|---------------------------------------|-------------|
| TARGET           | str               | Defines the target environment        | nci         |
| START_DATE       | date (YYYY-MM-DD) | Start date of the run                 | 2022-07-01  |
| END_DATE         | date (YYYY-MM-DD) | End date of the run                   | 2022-07-30  |
| STORE_PATH       | str               | Full path to the branch-specific data |             |
| EXPERIMENT       | str               | Name of the experiment being run      | 202207_test |
| PRIOR_PATH       | str               | Name of the experiment being run      | N/A         |
| MCIP_OUTPUT_PATH | str               | Path to the root MCIP directory       | N/A         |


For values with a default of N/A an exception will be raised if
the environment variable is not defined.