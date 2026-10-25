"""Publish validated tag artifacts and a linked GitHub Discussion from Actions."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ["RELEASE_TAG"]
    owner, name = repository.split("/")
    notes = Path(f".github/release-notes-{tag.removeprefix('v')}.md")
    if not notes.is_file():
        raise ValueError("Prepare reviewed release notes for this version before publishing")
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository], capture_output=True
    )
    if existing.returncode:
        gh(
            "release",
            "create",
            tag,
            "--verify-tag",
            "--repo",
            repository,
            "--title",
            f"{tag} — Recoverable indexing and reproducible retrieval evaluation",
            "--notes-file",
            str(notes),
            *map(str, sorted(Path("dist").glob("*"))),
        )
    query = """
query($owner:String!,$name:String!){repository(owner:$owner,name:$name){id
discussionCategories(first:25){nodes{id name}} 
discussions(first:50,orderBy:{field:CREATED_AT,direction:DESC}){nodes{title url}}}}
"""
    repo = json.loads(
        gh("api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}", "-f", f"name={name}")
    )["data"]["repository"]
    title = f"OmniChunk {tag}: recoverable RAG indexing and retrieval evaluation"
    if any(item["title"] == title for item in repo["discussions"]["nodes"]):
        return
    categories = repo["discussionCategories"]["nodes"]
    if not categories:
        raise RuntimeError(
            "Enable GitHub Discussions and create a category to publish the announcement"
        )
    category = next(
        (item for item in categories if item["name"].casefold() == "announcements"), categories[0]
    )
    mutation = """
mutation($repository:ID!,$category:ID!,$title:String!,$body:String!){
createDiscussion(input:{repositoryId:$repository,categoryId:$category,title:$title,body:$body}){discussion{url}}}
"""
    body = (
        notes.read_text()
        + f"\n\nRelease: https://github.com/{repository}/releases/tag/{tag}\n\n"
        + "What are you building with OmniChunk? Share your document types, integration needs, "
        + "and reproducible issues below. We especially welcome multilingual retrieval "
        + "evaluations and production indexing feedback.\n"
    )
    print(
        gh(
            "api",
            "graphql",
            "-f",
            f"query={mutation}",
            "-f",
            f"repository={repo['id']}",
            "-f",
            f"category={category['id']}",
            "-f",
            f"title={title}",
            "-f",
            f"body={body}",
        )
    )


if __name__ == "__main__":
    main()
