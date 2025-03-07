## 1. set up the environment
- make sure you have a python=3.9 conda environment for this repo
- then: `pip install -r requirements.txt`

## 2. make a small modification on the package
- for source file `<path_to_conda>/miniconda3/envs/<your_enc>/lib/python3.9/site-packages/pcpp/preprocessor.py`
- from line 1171, previously looks like: 
```python
            else:
                p = self.on_include_not_found(False,is_system_include,self.temp_path[0] if self.temp_path else '',filename)
                assert p is not None
                path.append(p)

``` 
- You need to modify it into:
```python
            else:
                p = self.on_include_not_found(False,is_system_include,self.temp_path[0] if self.temp_path else '',filename)
                if p is not None:
                    path.append(p)
                else:
                    return
```
- The reason is that we don't want to check for bad library including, we only do the code standard checking.