from typing import Iterable
from xml.etree.ElementTree import Element


def make_element(
    tag: str, text: str = "", children: Iterable | None = None, **kwargs
) -> Element:
    element = Element(tag, **kwargs)
    element.text = text
    if children:
        element.extend(children)
    return element
