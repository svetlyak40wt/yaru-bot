import copy
from lxml.html import clean
from lxml.html import tostring, fromstring, bytes


def _transform_result(typ, result):
    """Convert the result back into the input type.
    """
    if issubclass(typ, bytes):
        return tostring(result, encoding = 'utf-8', method = 'xml')
    elif issubclass(typ, unicode):
        return tostring(result, encoding = unicode, method = 'xml')
    else:
        return result



class Cleaner(clean.Cleaner):
    def clean_html(self, html):
        result_type = type(html)
        if isinstance(html, basestring):
            doc = fromstring(html)
        else:
            doc = copy.deepcopy(html)
        self(doc)
        return _transform_result(result_type, doc)

cleaner = Cleaner()
clean_html = cleaner.clean_html
