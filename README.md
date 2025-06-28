# free-proxy-generator-python
simple lightweight free open-source proxy validator in python. validating json output of https://github.com/proxifly/free-proxy-list?tab=readme-ov-file

This file was taken from a closed source project im working on and believed it would be useful for other developers

## Usage
TODO: for windows right now, but will add macos and linux soon

to use, put this in the required directory

this file was taken from this file structure:
app
|
|--->cache
|--->utils
      |
      |-->proxy.py


### PIP
`cd app && python -m venv venv && python -m pip install -r requirements.txt &&  .\.venv\Scripts\activate && python app/utils/proxy.py'`

### uv
`cd app && uv sync && .\.venv\Scripts\activate && uv run --script 'app/utils/proxy.py'`

feel free to modify it as you feel fit



