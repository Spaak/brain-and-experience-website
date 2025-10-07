import pandas as pd
import requests
from pathlib import Path
from rich import progress
from scidownl import scihub_download
import multiprocessing as mp


def fetch_apa_for_doi(doi):
    url = "https://dx.doi.org/" + str(doi)
    header = {"accept": 'text/x-bibliography; style=apa', 'User-Agent': 'eelke.spaak@donders.ru.nl'}
    r = requests.get(url, headers=header)
    return r.content.decode('UTF-8')


def post_process_apa_ref(ref):
    strip_strings = ['<i>', '</i>', ' (Version 1)', ' (Version 2)', ' (Version 3)', ' (Version 4)',
                     ' CLOCKSS.', ' Portico.']
    replace_strings = {'ELife': 'eLife',
                       'https://doi.org/10.1101/': 'bioRxiv. https://doi.org/10.1101/',
                       'Spaak, E.': '**Spaak, E.**'}

    for s in strip_strings:
        ref = ref.replace(s, '')
    for k, v in replace_strings.items():
        ref = ref.replace(k, v)

    return ref


def fetch_dois_from_orcid():
    orcid_id = "0000-0002-2018-3364"
    ORCID_RECORD_API = "https://pub.orcid.org/v3.0/"

    print("Retrieving ORCID entries from API...")
    response = requests.get(
        url=requests.utils.requote_uri(ORCID_RECORD_API + orcid_id),
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    orcid_record = response.json()

    df = []
    for iwork in progress.track(
        orcid_record["activities-summary"]["works"]["group"], "Fetching reference data..."
    ):
        
        # see if there are multiple entries for this work
        # often happens when there is both a preprint and a peer-reviewed version
        # choose the one with highest display-index (author preference)
        isummary = iwork['work-summary'][0]
        for summary in iwork['work-summary']:
            if summary['display-index'] > isummary['display-index']:
                isummary = summary

        year = isummary["publication-date"]["year"]["value"]

        # extract the DOI
        # we need to extract all the dois, because the above routine does not successfully filter
        # out preprints in all cases
        found_dois = []
        for ii in isummary["external-ids"]["external-id"]:
            if ii["external-id-type"] == "doi":
                found_dois.append(ii["external-id-value"])

        if found_dois:
            dois_ranked = assign_doi_ranks(found_dois)
            doi = dois_ranked[0]

            df.append({"year": year, "doi": doi})
    df = pd.DataFrame(df).drop_duplicates()
    return df


def assign_doi_ranks(dois):
    prefdois = {}
    for doi in dois:
        if doi.startswith('10.1101') or doi.startswith('10.48550'):
            # biorxiv or arxiv
            pref = 1 # higher pref means end up later in the list
        else:
            pref = 0
        prefdois[doi] = pref
    return list(dict(sorted(prefdois.items(), key=lambda x: x[1])).keys())


def generate_publication_list():
    dois = fetch_dois_from_orcid()

    outtext = ''
    cur_year = None

    print('Fetching APA references from doi.org...')
    # note: don't use more than 4 workers to avoid getting blocked
    with mp.Pool(4) as pool:
        allrefs = pool.map(fetch_apa_for_doi, dois['doi'])

    for ref, (k, row) in zip(allrefs, dois.iterrows()):
        if cur_year is None or row['year'] < cur_year:
            cur_year = row['year']
            outtext += '\n## ' + str(cur_year) + '\n\n'
        outtext += post_process_apa_ref(ref) + '\n'

    path_out = Path(__file__).parent / "pubs-formatted.md"
    path_out.write_text(outtext)
    print(f"Finished updating ORCID entries at: {path_out}")


def fetch_pdf_for_doi(doi):
    filename = doi.replace('/', '-')
    path_out = Path(__file__).parent.parent / 'static/pdf' / filename
    scihub_download(doi, out=str(path_out))


def fetch_all_pdfs():
    dois = fetch_dois_from_orcid()
    with mp.Pool(4) as pool:
        allrefs = pool.map(fetch_pdf_for_doi, dois['doi'])


if __name__ == '__main__':
    #fetch_all_pdfs()
    generate_publication_list()