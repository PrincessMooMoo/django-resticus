# Adapted from
# https://www.mysociety.org/2015/06/01/django-streaminghttpresponse-json-html/


class iterdict(dict):
    """This is a fake dict that sticks an iterable on items/iteritems. Why on
    earth would you want to do such a thing, I hear you cry? Well, if you want
    to output what you'd like to be a dict of c. 200,000 objects from a
    database, currently held in a lovely iterable, as JSON, but discover that
    json.iterencode() doesn't work with iterators, and that wouldn't be much
    help with a dict anyway, you either need to write your own iterator to
    output a JSON object, or trick iterencode() into thinking you're passing it
    a dict when you're not."""

    def __init__(self, source):
        self.source = iter(source)
        super().__init__({'hack': True})

    def items(self):
        return self.source

    def iteritems(self):
        return self.source


class iterlist(list):
    """This is a fake list that uses its own stored iterable. The built in json
    package, though it can work as an iterator using iterencode() or indeed
    dump(), can't take one as input, which is annoying if you're trying to save
    memory. This class can be passed to iterencode() and will work the same as
    a list, but won't require the list to exist first."""

    def __init__(self, source):
        self.source = iter(source)

        # iterencode() generates invalid json when iterlist
        # is empty and truthy. To fix this, we need to consume
        # the first item in the iterable and declare a proper
        # truthiness value for __bool__().
        try:
            self.first = next(self.source)
            self.empty = False
        except StopIteration:
            self.first = None
            self.empty = True
        super().__init__('hack')

    def __bool__(self):
        return not self.empty

    def __iter__(self):
        if self.empty:
            yield next(iter([]))
        else:
            yield self.first
            yield from self.source
