from pathlib import Path
import pandas as pd

from github_api import github_search
from queries import SEARCH_QUERIES

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "metadata" / "raw_sources.csv"

OUTPUT.parent.mkdir(exist_ok=True)
repositories = {}
source_counter = 1


def classify(query_group: str):

    if query_group == "trojan":
        return 1, "Benchmark"

    if query_group == "benchmark":
        return 2, "Academic"

    return 3, "Clean"


print("=" * 60)
print("HTBench Repository Discovery")
print("=" * 60)

for group, queries in SEARCH_QUERIES.items():

    print(f"\nSearching [{group}]")

    tier, category = classify(group)

    for query in queries:

        search = (
            query
            + " stars:>2"
            + " archived:false"
        )

        print(f"  -> {search}")

        try:

            items = github_search(search)

        except Exception as e:

            print(e)
            continue

        for repo in items:

            full_name = repo["full_name"]

            if full_name in repositories:
                continue

            repositories[full_name] = {

                "source_id": f"SRC{source_counter:04d}",

                "source_name": repo["name"],

                "tier": tier,

                "category": category,

                "owner": repo["owner"]["login"],

                "url": repo["html_url"],

                "stars": repo["stargazers_count"],

                "updated": repo["updated_at"],

                "language": repo["language"],

                "description": repo["description"],

                "status": "Discovered"

            }

            source_counter += 1

df = pd.DataFrame(repositories.values())

if df.empty:
    print("\nNo repositories found.")
    exit()

df = df.sort_values(
    by="stars",
    ascending=False
)

df.to_csv(OUTPUT, index=False)

print("\n")
print("=" * 60)
print("Discovery Complete")
print("=" * 60)
print(f"Repositories : {len(df)}")
print(f"Saved to      : {OUTPUT}")