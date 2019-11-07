#-------------------------------------------------------------------------------
# Name:        pagetrace
# Purpose:     Checks a website for a given string, either a piece of
#              visible text or a link, using breadth-first searching to
#              keep track of the route to each page from the homepage.
#
# Author:      aengelhart
#
# Created:     2019/06/24
# Copyright:   (c) aengelhart 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import csv
import requests
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from collections import deque

class Searcher(ABC):

    def __init__(self, top_page="index.php", filename="results.csv",
                     field_names=["Link Location"],
                     top_nav="nav", sub_nav="main",
                     site_prefix="",
                     criteria=""):
        """
        Base Searcher class.

        Subclasses must implement check_for_criteria(tag, current_page)

        Searches for a given criteria from a given website, starting
        from a given homepage and using breadth-first search to recurse through
        the sitemap as accessible via <a> tags on that page.

        Keyword arguments:
            site_prefix -- Protocol through top-level domain. Must include
                           trailing slash (e.g. "http://www.example.com/")
            top_page -- The first page to search.  Will usually be something
                        on the order of "index.php."  Empty string is untested.
            top_nav -- The id of the HTML tag on the top page that will
                       serve as the target of the search.  Note that this class
                       will NOT search past the closing tag.
            sub_nav -- As top_nav, but for all subpages past the top page.
            criteria -- The search criteria, given as a string.
            filename -- File name for the search results CSV file.
                        Defaults to saving in same folder as this script.
                        TODO: default to Documents
            field_names -- Field names for data in the results CSV file.

        Also defined in this class:
            self.traversed_urls -- contains list of all URLs searched at any
                                   given point in time
            self.page_queue -- A Collections.deque instance implementing a queue
                               of all pages to be searched


        TODO: refactor such that the three search functions (from_top,
        from_subpage, recursive_search) can be made private (or at least as
        private as Python allows).
        """

        self.__dict__.update(locals())
        if self.site_prefix.endswith("/") == False:
            self.site_prefix += "/"
        with open(filename, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()

        #Diagnostic file - contains all pages visited with queue counts
        with open("net_pagelog.csv", "w") as f:
            f.write("")
        self.traversed_pages = []
        #TODO: kill this across the board
        self.traversed_urls = []
        self.page_queue = deque([])

    def _shorten(self, url):
        """Shorten a URL by collapsing double-dot notation.

        Example: self._shorten("foo/bar/../baz/../rat/") == "foo/rat/"
        """
        s = url.split("/")
        while ".." in s:
            i = s.index("..")
            s.pop(i)
            s.pop(i - 1)
        new_str = ""
        for i in s:
            if i != "":
                new_str += i + "/"
        return new_str

    def write_csv(self, row):
        """Writes a row of output to self.filename"""
        with open(self.filename, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def tracelog(self, current_page):
        """Writes current page trace to self.filename, from top page to bottom.

        Should be overwritten if subclass needs to record something other
        than a page trace (ex. DocSearcher needs to print filenames with
        link text).
        """
        if isinstance(current_page, PageListing) == False:
            raise TypeError("Tracelog must take PageListing as argument")
        for i in current_page.from_parent():
            self.write_csv((i.url,))
        self.write_csv(("-----",))

    def from_top(self):
        """
        Initializes parameters and runs first search.

        Creates top-level PageListing instance containing self.top_page,
        enqueues it into self.page_queue, then runs first search.

        If PageNotFoundError is raised when getting page structure,
        prints warning and passes empty string to recursive_search, which will
        cause it to return False.
        """
        top_page_listing = PageListing(self.top_page)
        self.page_queue.append(top_page_listing)
        try:
            page_structure = self.get_page_structure(self.page_queue[0],
                                                             start=self.top_nav)
        except PageNotFoundError as e:
            print("Page not found: "
                 + self.site_prefix + e.url +". Please check your spelling.")
            page_structure = ""

        return_code = self.recursive_search(page_structure)
        return return_code

    def recursive_search(self, tag):
        """Checks tags for criteria, then iterates through internal links.

        Returns True unless no tag is given, which should only occur if
        from_top calls it with an empty string.
        """
        if tag == "":
            return False
        current_page = self.page_queue.popleft()
        current_page.url = self._shorten(current_page.url)
        if self.site_prefix + current_page.url in self.traversed_urls:
            raise RepeatTraversalError("Page visited twice: ",
                                         current_page.url)
        self.traversed_pages.append(current_page)
        self.traversed_urls.append(self.site_prefix + current_page.url)
        stop_checking = False
        for c in tag.descendants:
            if type(c).__name__ == "Tag":
                if stop_checking == False:
                   stop_checking = self.check_for_criteria(c, current_page)
                if (c.name == u'a'
                    and 'href' in c.attrs
                    and c['href'].startswith('http') == False
                    and c['href'].endswith('php') == True
                    and ((self.site_prefix + c['href'])
                            not in self.traversed_urls)):
                        self.page_queue.append(PageListing(c['href'],
                                                      current_page))
        return self.from_subpage()

    def get_page_structure(self, current_page, start="main"):
        """
        Returns requested HTML page structure.

        Performs a GET request for current page, then returns a
        BeautifulSoup object containing the tag where id == start
        (or the entire body if start == ""). Raises PageNotFoundError
        if request returns anything other than a HTTP 200 code.
        """
        #For testing using HTML files saved to hard drive
        if(self.site_prefix.lower().startswith("c:\\")):
            with open(self.site_prefix + current_page.url) as f:
                if start == "":
                    return BeautifulSoup(f,"html.parser").body
                return BeautifulSoup(f,"html.parser").find(id=start)
        else:
            page = requests.get(self.site_prefix + current_page.url)
            if page == None or page.status_code != 200:
                raise PageNotFoundError(getattr(page, "status_code", None),
                                        current_page.url)
            if start == "":
                return BeautifulSoup(page.content, "html.parser").body
            return BeautifulSoup(page.content, "html.parser").find(id=start)

    def from_subpage(self, start="main"):
        page_structure = None
        my_url = ""
        while len(self.page_queue) > 0:
            current = self.page_queue[0]
            my_url = self._shorten(current.url)
            if self.site_prefix + my_url in self.traversed_urls:
                #print("Found again: " + self.page_queue.popleft().url)
                self.page_queue.popleft()
            else:
                try:
                    page_structure = self.get_page_structure(current)
                except PageNotFoundError as e:
                    print(e.message + " " + self.page_queue.popleft().url)
                    if len(self.page_queue) == 0:
                        return
                else:
                    break

        with open("net_pagelog.csv", "a") as f:
            writer = csv.writer(f)
            try:
                writer.writerow((len(self.page_queue[0]),
                                my_url,
                                len(self.page_queue)))
            except IndexError:
                pass
        if page_structure == None and len(self.page_queue) == 0:
            return True
        else:
             return self.recursive_search(page_structure)

    @abstractmethod
    def check_for_criteria(self, tag, current_page):
        """Base class checks type and returns False. Implement checking here.

        Subclasses should return stop_checking, which should return False if:
            - criteria has not been met, or
            - criteria needs to be checked on a per-item basis, not per-page.
        """
        if current_page == None:
            raise TypeError("No page given to check with tag")
        stop_checking = False
        return stop_checking

class TextSearcher(Searcher):
    """Searches page text for string"""

    def check_for_criteria(self, tag, current_page):
        stop_checking = super().check_for_criteria(tag, current_page)
        try:
            stop_checking = (self.criteria.lower() in tag.string.lower())
        except:
            stop_checking = False
        if stop_checking:
            self.tracelog(current_page)
        return stop_checking

class LinkSearcher(Searcher):
    """Searches links for a URL"""
    def check_for_criteria(self, tag, current_page):
        super().check_for_criteria(tag, current_page)
        stop_checking = (tag.name == u'a'
                        and getattr(tag, "href", None) == self.criteria)
        if stop_checking:
            self.tracelog(current_page)
        return stop_checking

class DocSearcher(Searcher):
    """Searches for all documents visible on the site"""
    def __init__(self, *args, **kwargs):
        self.doctypes = (".pdf", ".ppt", ".pptx", ".doc", ".docx")
        super().__init__(self,
                         field_names=["Location", "Doc Name", "Link Text"],
                         filename="all_docs.csv",
                         *args, **kwargs)

    def check_for_criteria(self, tag, current_page):
        if current_page == None:
            raise TypeError("No page given to check with tag")
        elif tag.name == u'a' and 'href' in tag.attrs:
            for d in self.doctypes:
                if d in tag['href']:
                    self.write_csv((current_page.url, tag['href'],
                                    str(getattr(tag, "string", "--blank--"))))
        return False #Base class stops search on a return of True


class BlankPageSearcher(Searcher):
    """Searches for all pages containing no text or just placeholder text"""
    def __init__(self, *args, **kwargs):
        super().__init__(self, filename="blank_pages.csv",
                                *args, **kwargs)

    def recursive_search(self, tag):
        """check_for_criteria is run on page itself here, not over tags"""

        current_page = self.page_queue.popleft()
        current_page.url = self._shorten(current_page.url)
        if self.site_prefix + current_page.url in self.traversed_urls:
            raise RepeatTraversalError("Page visited twice",
                                        current_page.url)
        self.traversed_pages.append(current_page)
        self.traversed_urls.append(self.site_prefix + current_page.url)
        self.check_for_criteria(tag, current_page)
        for c in tag.descendants:
            if type(c).__name__ == "Tag":
                if (c.name == u'a'
                    and 'href' in c.attrs
                    and c['href'].startswith('http') == False
                    and c['href'].endswith('php') == True
                    and ((self.site_prefix + c['href'])
                            not in self.traversed_urls)):
                        self.page_queue.append(PageListing(c['href'],
                                                      current_page))
        self.from_subpage()

    def check_for_criteria(self, tag, current_page=None):
        if isinstance(tag, PageListing): #only one argument provided
            current_page = tag
            tag = None
        criteria_met = super().check_for_criteria(tag, current_page)
        if tag == None:
            tag = self.get_page_structure(current_page.url)
        subtag = tag.find(class_="post clearfix")
        #if True, has only an edit button
        if subtag != None:
            criteria_met = (len(subtag.contents) < 4
                            or (len(subtag.contents) == 4
                                and (subtag.contents[3] == '\n'))
                            ) or False
            if not criteria_met:
                for i in subtag.strings:
                    if "Update 7/19" in i:
                        criteria_met = True

        if criteria_met:
            for i in current_page.from_parent():
                self.write_csv((i.url,))
            self.write_csv(("-----",))
        return True #only run this once



class ImageSearcher(Searcher):
    """Searches for all images, returns URL, filename and any alt text"""
    def __init__(self, *args, **kwargs):
        Searcher.__init__(self, filename="image_list.csv",
                          field_names=["Page", "File", "Alt Text"],
                          top_nav="")

    def check_for_criteria(self, tag, current_page):
        if tag.name == u'img':
            alt = None
            if "alt" in tag.attrs:
                alt = str(tag["alt"])
            self.write_csv((current_page.url,
                            tag['src'],
                            alt if alt != None else "--blank"))
        return False


class BadLinkSearcher(Searcher):
    """Searches for internal links that return other than a success code"""
    def __init__(self, *args, **kwargs):
        Searcher.__init__(self, filename="bad_links.csv", *args, **kwargs)

    #Functionality being moved to self.get_page_structure()
    def check_for_criteria(self, tag=None, current_page=None):
        return True

    def get_page_structure(self, current_page, start="main"):
        page = requests.get(self.site_prefix + current_page.url)
        if page == None or page.status_code != 200:
            self.tracelog(current_page)
            raise PageNotFoundError(getattr(page, "status_code", None),
                                    current_page.url)

        if start == "":
            return BeautifulSoup(page.content, "html.parser").body
        return BeautifulSoup(page.content, "html.parser").find(id=start)

"""
class GenerateTree(Searcher):
    import xml.etree.ElementTree as ET

    def __init__(self, *args, **kwargs):
        Searcher.__init__(self, *args, **kwargs)
        self.tree = TreeNode(self.top_page)
"""

class PageListing:
    def __init__(self, url, trace=None):
        self.url = url
        if trace != None and isinstance(trace, PageListing) == False:
            raise TypeError(
                         "Child pages must have PageListing as second argument")
        self.trace = trace

    def __len__(self):
        i = 0
        for p in self.from_child():
            i += 1
        return i

    def __str__(self):
        s = ""
        for p in self.from_parent:
            s += p.url + "\n"
        return s

    def __iter__(self):
        """Default iterator starts from child"""
        return self.from_child()

    def from_child(self):
        """Iterate through listings starting at self and going to last trace"""
        p = self
        while p != None:
            yield p
            p = p.trace

    def from_parent(self):
        """Iterate through listings starting at last trace and going to self"""
        a = []
        p = self
        while p != None:
            a.append(p)
            p = p.trace
        while len(a) > 0:
            yield a.pop()

    def copy(self):
        """Returns deep copy of self."""
        if self.trace == None:
            return PageListing(self.url)
        return PageListing(self.url, self.trace.copy())


class TreeNode:
    def __init__(self, value, parent=None, children=None):
        """Node for sitemap tree.

        Arguments:
            value -- The value stored in the node
            parent -- Reference to the parent node, if any. If parent == None,
                      this node is presumed to be the root.
            children -- Either a single TreeNode or a list thereof.

        """
        self.value = value
        self.parent = parent
        if children == None:
            self.children = []
        else:
            if isinstance(children, list):
                for i in children:
                    if isinstance(i, TreeNode):
                        self.children.append(i)
                    else:
                        raise TypeError("List must contain TreeNode references")
            elif isinstance(children, TreeNode):
                self.children.append(children)
            else:
                raise TypeError("Children must be list or single TreeNode")

    def is_root(self):
        if self.parent == None:
            return True
        else:
            return False

    def new_child(self, new_node):
        """Add new child node to this node.

        Order of self.children is arbitrary
        """
        if isinstance(new_node, TreeNode):
            if new_node.is_root() == False:
                raise ValueError("Node already child of another tree")
            new_node.parent = self
            self.children.append(new_node)
            assert self.children[-1] is new_node
        else:
            self.children.append(TreeNode(new_node, self))

    def search(self, search_value):
        """Breadth-first search"""
        q = deque([])
        q.append(self)
        while len(q) > 0:
            if q[0].value == search_value:
                return q[0]
            for i in q[0].children:
                q.append(i)
            q.popleft()

        return None





class PageError(Exception):
    def __init__(self, message, url):
        self.message = message
        self.url = url

class RepeatTraversalError(PageError):
    pass

class PageNotFoundError(PageError):
    pass

