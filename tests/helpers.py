
def read_file(path):
    with path.open() as f:
        return f.read()


def write_file(path, content):
    with path.open('w') as f:
        f.write(content)
    return path
