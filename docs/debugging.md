## Fetching results from S3

For local testing it is useful to fetch the results from a previous run to use as a starting point.

The following command will fetch the results from the S3 bucket `BUCKET_NAME` for the `aust-nsw` region for the month of July 2022.

```bash
aws-vault exec openmethane-sandbox-admin -- aws s3 sync s3://{BUCKET_NAME}/aust-nsw/monthly/2022/07 data/aust-nsw/monthly/2022/07 --exclude 'prior/intermediates/*' --exclude 'cams/*'
```

The CAMs and prior intermediate data are used in during the preprocessing step, but aren't needed if you are just wanting to run the model.
