# Replication_AG

# Running
## Step (1) 
Make sure to to download all of the requirements in the requirements.txt into a virtual environment so that you can run the python code. 

## Step (2) 
Run 'download_html.py' in main. 

This will download all of the information from the DoD website and store it locally. 

## Step (3) Run 'dod_webscrape.py'

This will walk through all of the saved html files and extract the relevant information into two files: 
- webscraped_data.csv
- correction.csv

# Note

This webscraping is not full proof and still produces errors due to the inconsistency in formatting from the websites that are looked at. 