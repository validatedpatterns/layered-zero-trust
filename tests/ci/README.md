# The requirements.txt file is just a placeholder to show the installed packages in the utility container
https://github.com/validatedpatterns/utility-container/blob/main/requirements.txt

# The ci will run pytest based on file pattern
pytest -lv test_<TARGET_CLUSTERGROUP>.py --junit-xml .results/test_<TARGET_CLUSTERGROUP>.xml

# To run upstream tests locally
Set the env variables pointing to the clusters needed to run the tests on:  
```HUBCONFIG``` (```SPOKECONFIG``` if applicable) pointing to the kubconfig of hub (and spoke) clusters  
```TARGET_CLUSTERGROUP``` if its different from the default (values-global.yaml main.clusterGroupName)  
Test logs and junit-xml will be saved in ci/.results/  
Run from repo root
```bash
./pattern.sh make run-ci-tests
```

# Writing additonal tests
The openshift_dyn_client fixture will return a DynamicClient which can be used inside test functions.  
It requires only an env variable param to use it as a kubeconfig.  
```python
@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["HUBCONFIG"],
    indirect=True,
)
```
If your tests requires additional python packages, you might want to either run them fully locally in a venv or similar.  
Or if you want to use the pattern framework (make/ansible wrappers) you need to use your own util container
```bash
PATTERN_UTILITY_CONTAINER="your_utility container" ./pattern.sh make run-ci-tests

```