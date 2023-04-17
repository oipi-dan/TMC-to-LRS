from AutoQC import run_AutoQC
import arcpy
import config
import pandas as pd

def run_AutoQC_55():
    run_AutoQC('_55', feature_class='data/scrap.gdb/_50_tmc_events')

    print('\nResetting failed QC results')
    # Load failing QC results
    qc_results = f'data//_55_AutoQC.csv'
    qc = pd.read_csv(qc_results, usecols=['tmc','confidence'])
    qc = qc.loc[qc['confidence'] < 70] # Reduce to only failed records

    # Get list of failed TMCs
    failed_tmcs = qc['tmc'].tolist()

    # Set status to null for failed QC results
    with arcpy.da.UpdateCursor(config.TMCs, ['tmc', 'status', 'rte_nm', 'begin_msr', 'end_msr']) as cur:
        for row in cur:
            if row[0] in failed_tmcs:
                row[1] = 'Failed QC (55)'
                # row[2] = None
                # row[3] = None
                # row[4] = None

                cur.updateRow(row)


if __name__ == '__main__':
    print('\nRunning AutoQC')
    run_AutoQC_55()