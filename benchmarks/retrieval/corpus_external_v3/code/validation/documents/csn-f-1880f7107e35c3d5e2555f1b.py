def list_tickers(self, assetType):
        
        listing_file_url = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
        response = requests.get(listing_file_url)
        zipdata = get_zipfile_from_response(response)
        raw_csv = get_buffer_from_zipfile(zipdata, 'supported_tickers.csv')
        reader = csv.DictReader(raw_csv)

        return [row for row in reader
                if row.get('assetType') == assetType]
