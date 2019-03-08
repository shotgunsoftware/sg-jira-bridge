# Examples


Some custom syncer examples which can be useful if you need to implement your own syncing
logic:

- **`example_sync`**: A simple example showing how custom settings can be used in a custom syncer.
- **`asset_hierarchy`**: An example showing how a Shotgun Asset/Task hierarchy can be reproduced in Jira with dependency links between Issues.

These examples can be loaded if this `examples` directory is added to the PYTHONPATH in your `settings.py`

For example:
```python
# Add the examples folder to the Python path so the syncers can be loaded.
sys.path.append(os.path.abspath("./examples"))

SYNC = {
    # Add the test syncer to the list of syncers, it will be available
    # with the http://<your server>/jira2sg/test and http://<your server>/sg2jira/test 
    # urls.
    "test": {
        # Example of a custom syncer with an additional parameter to define
        # a log level.
        "syncer": "example_sync.ExampleSync",
        "settings": {
            "log_level": logging.DEBUG
        },
    }
}
```
