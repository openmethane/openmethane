"""Run the WRF weather model to produce the meteorology for CMAQ.

The modules here decide what to run: configuration, domain geometry, run
windows, namelists, MPI ranks and the output layout. They are pure, and read
no configuration on import.
"""
