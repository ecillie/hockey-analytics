"""Small dependency-free HTML tree for retained source documents."""
from html.parser import HTMLParser
import json


class Node:
    def __init__(self, tag="root", attrs=None):
        self.tag, self.attrs, self.children = tag, attrs or {}, []

    def text(self):
        return " ".join(" ".join(child if isinstance(child, str) else child.text()
                                 for child in self.children).split())

    def descendants(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.descendants(tag)


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root, self.stack = Node(), []
        self.stack.append(self.root)
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)

    def next_data(self):
        scripts = [node for node in self.root.descendants("script") if node.attrs.get("id") == "__NEXT_DATA__"]
        if len(scripts) != 1:
            raise ValueError("Source response lacks a unique __NEXT_DATA__ document")
        # Whitespace within JSON strings must be preserved.
        data = json.loads("".join(child for child in scripts[0].children if isinstance(child, str)))
        if not isinstance(data, dict):
            raise ValueError("Source data document is not an object")
        return data
