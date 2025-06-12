pandas.errors.EmptyDataError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/mount/src/box-order-packing-checker/packing_checker.py", line 242, in <module>
    main()
    ~~~~^^
File "/mount/src/box-order-packing-checker/packing_checker.py", line 234, in main
    results_page()
    ~~~~~~~~~~~~^^
File "/mount/src/box-order-packing-checker/packing_checker.py", line 62, in results_page
    orders = pd.read_csv(orders_file, dtype=str)
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/parsers/readers.py", line 1026, in read_csv
    return _read(filepath_or_buffer, kwds)
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/parsers/readers.py", line 620, in _read
    parser = TextFileReader(filepath_or_buffer, **kwds)
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/parsers/readers.py", line 1620, in __init__
    self._engine = self._make_engine(f, self.engine)
                   ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/parsers/readers.py", line 1898, in _make_engine
    return mapping[engine](f, **self.options)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/pandas/io/parsers/c_parser_wrapper.py", line 93, in __init__
    self._reader = parsers.TextReader(src, **kwds)
                   ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
File "pandas/_libs/parsers.pyx", line 581, in pandas._libs.parsers.TextReader.__cinit__
