#! /bin/bash

pip install /windows

pip install -r requirements.txt

rm -r /app/dist

pyinstaller production.spec



