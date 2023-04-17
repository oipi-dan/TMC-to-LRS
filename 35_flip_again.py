""" The TMCs that are matched in 31_identify_routes_by_number_name are
    'flipped' here - any TMC where the begin_msr is higher then the end_msr
    is assumed to represent the non-prime direction and the TMC is placed
    on the non-prime route on the LRS.
"""
import flip_routes

def flip_routes_again():
    sql = "status = 'Complete (30)'"  # Only run on routes that have already been matched
    flip_routes.run_flip_routes(' - Flipped (35)', sql)


if __name__ == '__main__':
    print('\nFlipping routes identified in 31_identify_routes_by_number_name.py')
    flip_routes_again()