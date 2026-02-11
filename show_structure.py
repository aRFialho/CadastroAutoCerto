from pathlib import Path


def show_tree(directory, prefix="", max_depth=3, current_depth=0):
    if current_depth > max_depth:
        return

    directory = Path(directory)
    items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))

    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = "└── " if is_last else "├── "
        print(f"{prefix}{current_prefix}{item.name}")

        if item.is_dir() and not item.name.startswith('.') and item.name not in ['__pycache__', 'build', '.git']:
            extension = "    " if is_last else "│   "
            show_tree(item, prefix + extension, max_depth, current_depth + 1)


print("📁 ESTRUTURA DO PROJETO:")
show_tree(".")