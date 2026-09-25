from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
TEXTS = ROOT / "texts"
OUTPUT = ROOT / "files.json"

def build_tree(folder: Path):
    children = []

    if not folder.exists():
        folder.mkdir(parents=True)

    entries = sorted(
        folder.iterdir(),
        key=lambda p: (p.is_file(), p.name.lower())
    )

    for path in entries:
        if path.name.startswith("."):
            continue

        if path.is_dir():
            children.append({
                "name": path.name,
                "type": "folder",
                "children": build_tree(path)
            })

        elif path.suffix.lower() == ".txt":
            relative = path.relative_to(ROOT).as_posix()
            children.append({
                "name": path.name,
                "type": "file",
                "path": relative
            })

    return children

tree = {
    "name": "texts",
    "type": "folder",
    "children": build_tree(TEXTS)
}

OUTPUT.write_text(
    json.dumps(tree, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

def count_items(node):
    files = folders = 0
    for child in node.get("children", []):
        if child["type"] == "file":
            files += 1
        else:
            folders += 1
            f, d = count_items(child)
            files += f
            folders += d
    return files, folders

files, folders = count_items(tree)

print("files.json berhasil diperbarui.")
print(f"Folder: {folders}")
print(f"File .txt: {files}")
