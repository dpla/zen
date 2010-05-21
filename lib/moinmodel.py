# -*- coding: iso-8859-1 -*-
# 
"""

See: http://wiki.xml3k.org/Akara/Services/MoinCMS

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

@copyright: 2009 by Uche ogbuji <uche@ogbuji.net>


T = ''' title::  httplib2 0.6.0 
 last changed:: 2009-12-28T13:06:56-05:00
 link:: http://bitworking.org/news/2009/12/httplib2-0.6.0
= Summary =
None
= akara:metadata =
 akara:type:: http://purl.org/com/zepheira/zen/resource/webfeed
'''

from amara.tools.creoletools import parse
from amara.writers import lookup
from zenlib import moinmodel

doc = parse(T)
#doc.xml_write(lookup('xml-indent'))
n = moinmodel.node(doc, 'http://localhost:8880/moin/mywiki/spam/eggs', 'http://localhost:8080/spam/eggs')
print n.akara_type()

"""

import hashlib
import datetime
import urllib, urllib2
from gettext import gettext as _

from dateutil.parser import parse as dateparse

from functools import wraps, partial

import amara
from amara import tree, bindery
from amara.bindery import html
from amara.lib.util import first_item
from amara.lib import inputsource
#from amara import inputsource as baseinputsource
from amara.lib.irihelpers import resolver as baseresolver
#from amara.namespaces import *
#from amara.xslt import transform
#from amara.writers.struct import *
#from amara.bindery.html import parse as htmlparse
from amara.lib import U
from amara.lib.iri import split_fragment, relativize, absolutize, IriError
#from amara.bindery.model import examplotron_model, generate_metadata, metadata_dict
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter

from akara import httplib2
from akara.util import copy_auth
from akara.util.moin import wiki_uri, ORIG_BASE_HEADER, DOCBOOK_IMT, RDF_IMT, HTML_IMT, XML_IMT

try:
    from akara import logger
except ImportError:
    logger = None

from zenlib import zservice

def cleanup_text_blocks(text):
    return '\n'.join([line.strip() for line in text.splitlines() ])


def linkify(link, wikibase):
    '''
    Try to construct Moin-style link markup from a given link
    '''
    rel = relativize(link, wikibase)
    if rel:
        return u'[[%s]]'%rel
    else:
        return u'[[%s]]'%link

#class construct(object):
#    '''
#    A data construct derived from a Moin wiki page
#    '''
#    def load(self):
#        raise NotImplementedError

class moinrest_resolver(baseresolver):
    """
    Resolver that uses a specialized URL opener
    """
    def __init__(self, authorizations=None, lenient=True, opener=None):
        """
        """
        self.opener = opener or urllib2.build_opener()
        self.last_lookup_headers = None
        baseresolver.__init__(self, authorizations, lenient)

    def resolve(self, uri, base=None):
        if not isinstance(uri, urllib2.Request):
            if base is not None:
                uri = self.absolutize(uri, base)
            req = urllib2.Request(uri)
        else:
            req, uri = uri, uri.get_full_url()
        try:
            #stream = self.opener(uri)
            resp = self.opener.open(req)
            stream = resp
            self.last_lookup_headers = resp.info()
        except IOError, e:
            raise IriError(IriError.RESOURCE_ERROR,
                               uri=uri, loc=uri, msg=str(e))
        return stream


#FIXME: consolidate URIs, opener, etc. into an InputSource derivative
#class inputsource(baseinputsource):
#    def __new__(cls, arg, uri=None, encoding=None, resolver=None, sourcetype=0, opener=None):
#       isrc = baseinputsource.__new__(cls, arg, uri, encoding, resolver, sourcetype)
#        isrc.opener = opener
#        return isrc

#    def __init__(self, arg, uri=None, encoding=None, resolver=None, sourcetype=0, opener=None):
#        baseinputsource.__init__(cls, arg, uri, encoding, resolver, sourcetype)

RESOURCE_TYPE_TYPE = 'http://purl.org/xml3k/akara/cms/resource-type'


UNSPECIFIED = object()

class node(object):
    '''
    Akara Moin/CMS node, a Moin wiki page that follows a template to direct workflow
    activity, including metadata extraction
    '''
    AKARA_TYPE = u'http://purl.org/xml3k/akara/cms/resource-type'
    NODES = {}
    ENDPOINTS = None

    _instance_cache = {}
    H = httplib2.Http('.cache')

    @staticmethod
    def lookup(rest_uri, opener=None, resolver=None):
        '''
        rest_uri - URI of the moinrest-wrapped version of the page
        opener - for specializing the HTTP request (e.g. to use auth)
        '''
        if rest_uri in node._instance_cache:
            #FIXME: Check for cache invalidation first. Right now this cache will last as long as the akara process
            return node._instance_cache[rest_uri]
        if not resolver:
            resolver = moinrest_resolver(opener=opener)
        if logger: logger.debug('rest_uri: ' + rest_uri)
        isrc, resp = parse_moin_xml(rest_uri, resolver=resolver)
        doc = bindery.parse(isrc)
        #doc = bindery.parse(isrc, standalone=True, model=MOIN_DOCBOOK_MODEL)
        original_base, wrapped_base, original_page = resp.info()[ORIG_BASE_HEADER].split()
        atype = resource_type.construct_id(doc, original_base, wrapped_base, rest_uri)
        #Older Moin CMS resource types are implemented by registration to the global node.NODES
        #Newer Moin CMS resource types are implemented by discovery of a URL,
        #to which a POST request executes the desired action
        cls = node.NODES.get(atype, node)
        instance = cls(doc, rest_uri, original_base, wrapped_base, akara_type=atype, resolver=resolver)
        node._instance_cache[rest_uri] = instance
        return instance
        #return node.ENDPOINTS and (rest_uri, akara_type, node.ENDPOINTS[akara_type], doc, metadata, original_wiki_base)

    @staticmethod
    def create(resource_type, body, ctype, opener=None, resolver=None):
        '''
        resource_type - type of the new resource to be created
        body - input information or document required to construct the resource page, according to the rule sheet
        '''
        if not resolver:
            resolver = moinrest_resolver(opener=opener)
        resource_type = node.lookup(resource_type, resolver=resolver)
        handler = resource_type.run_rulesheet('POST', ctype)
        url, wikified = handler(body)

        resp, content = self.H.request(url, "PUT", body=wikified, headers={'Content-Type' : 'text/plain'})

        return
    
    def __init__(self, doc, rest_uri, original_base, wrapped_base, akara_type=None, resolver=None):
        '''
        rest_uri - the full URI to the Moin/REST wrapper for this page
        relative - the URI of this page relative to the Wiki base
        '''
        self.doc = doc
        self.rest_uri = rest_uri
        self.original_base = original_base
        self.wrapped_base = wrapped_base
        self.resolver = resolver
        self.rulesheet = None
        self.resource_type = None
        if node.ENDPOINTS and akara_type in node.ENDPOINTS:
            #Uses old-style Akara services registered to endpoints
            self.endpoint = node.ENDPOINTS[akara_type]
        else:
            #Uses rulesheets
            self.endpoint = None
            #FIXME: Inelegant not to use polymorphism for the RESOURCE_TYPE_TYPE test
            if isinstance(akara_type, basestring) and akara_type != RESOURCE_TYPE_TYPE:
                try:
                    self.resource_type = node.lookup(akara_type, resolver=self.resolver)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    #If there is an error looking up the resource type, just leave off.  Some operations will then fail
                    logger.debug('Exception looking up resource type %s: %s'%(akara_type, repr(e)))
                    pass
        return

    def load(self):
        raise NotImplementedError

    #def render(self):
    #    raise NotImplementedError

    def up_to_date(self, force_update=False):
        '''
        Checks whether there needs to be an update of the output
        '''
        #By default just always update
        return False

    def akara_type(self):
        return resource_type.construct_id(self.doc, self.original_base, self.wrapped_base, self.rest_uri)

    def section(self, title):
        '''
        Helper to extract content from a specific section within the page
        '''
        #FIXME: rethink this "caching" business
        logger.debug("section_titled: " + repr(title))
        return first_item(self.doc.xml_select(u'//*[@title = "%s"]'%title))

    def definition_list(self, list_path, contextnode=None, patterns=None):
        '''
        Helper to construct a dictionary from an indicated definition list on the page
        '''
        #FIXME: rethink this "caching" business
        #Use defaultdict instead, for performance
        #patterns = patterns or {None: lambda x: U(x) if x else None}
        patterns = patterns or {None: lambda x: x}
        contextnode = contextnode or self.doc.s1
        top = contextnode.xml_select(list_path)
        if not top:
            return None
        #Go over the glossentries, and map from term to def, applying the matching
        #Unit transform function from the patterns dict
        result = dict((U(l), patterns.get(U(l), patterns[None])(first_item(l.xml_select(u'following-sibling::item'))))
                      for l in top[0].label)
        logger.debug("definition_list: " + repr(result))
        return result

    def definition_section(self, title, patterns=None):
        '''
        Helper to extract the first definition list from a named section
        '''
        return self.definition_list(u'.//gloss', contextnode=self.section(title), patterns=patterns)
        
    def list_section(self, title):
        '''
        Helper to extract all list items from a section
        '''
        #XXX: Should support flattening lists, or even returning nested lists
        l = self.section(title).xml_select(u'.//ul')[0]
        return list(l.li)

    def get_proxy(self, method, accept=None):
        return self.resource_type.run_rulesheet(method, accept)

    def absolute_wrap(self, link):
        link = '/' + link.lstrip('/')
        #if logger: logger.debug('absolute_wrap: ' + repr((self.original_base, self.wrapped_base, link, self.rest_uri)))
        wrapped_link, orig_link = wiki_uri(self.original_base, self.wrapped_base, link, self.rest_uri)
        #if logger: logger.debug('absolute_wrap: ' + repr((link, wrapped_link, orig_link)))
        return wrapped_link


node.NODES[node.AKARA_TYPE] = node

def parse_moin_xml(uri, resolver=None):
    #Stupid Moin XML export uses bogus nbsps, so this function encapsulates the kludge
    if logger: logger.debug('parse_moin_xml: ' + repr((uri,)))
    req = urllib2.Request(uri, headers={'Accept': XML_IMT})
    resp = urllib2.urlopen(req)
    body = resp.read()
    return inputsource(body.replace('&nbsp;', '&#160;').replace('<p><p>', '<p></p>').replace('<p></s2>', '</s2>'), resolver=resolver), resp


class rulesheet(object):
    def __init__(self, source):
        '''
        '''
        rs = inputsource(source)
        self.token = rs.stream.readline().strip().lstrip('#')
        self.body = rs.stream.read()
        return

    #
    def run(self, resource, method='GET', accept='application/json'):
        #e.g. you can sign a rulesheet as follows:
        #python -c "import sys, hashlib; print hashlib.sha1('MYSECRET' + sys.stdin.read()).hexdigest()" < rsheet.py 
        #Make sure the rulesheet has not already been signed (i.e. does not have a hash on the first line)
        if self.token != hashlib.sha1(node.SECRET + self.body).hexdigest():
            raise RuntimeError('Security token verification failed')
        #chunks = []
        def U1(text): return U(text, noneok=True)
        #def write(text):
        #    chunks.append(text)

        handlers = {}
        #Decorator that allows the user to define request handler functions in rule sheets
        def handles(method, match=None, ttl=3600):
            '''
            method - HTTP method for this handler to use, e.g. 'GET' or 'PUT'
                     Might be a non-standard, internal method for special cases (e.g. 'collect')
            match - condition to determine when this handler is to be invoked for a given method
                    if a Unicode object, this should be an IMT to compare to the Accept info for the request
                    if a callable, should have signature match(accept), return ing True or False
            ttl - time-to-live for (GET) requests, for setting cache-control headers
            '''
            def deco(func):
                func.ttl = ttl
                handlers.setdefault(method, []).append((match, func))
                return func
            return deco

        #env = {'write': write, 'resource': self, 'service': service, 'U': U1}
        resource_getter = partial(node.lookup, resolver=resource.resolver)
        env = {'service': service, 'U': U1, 'handles': handles, 'R': resource_getter}

        #Execute the rule sheet
        exec self.body in env
        default = None
        matching_handler = None
        for (match, func) in handlers.get(method, []):
            if logger: logger.debug('(match, func): ' + repr((match, func)))
            if isinstance(match, basestring):
                if match == accept:
                    matching_handler = func
            elif match is None:
                default = func
            else:
                if match(accept):
                    matching_handler = func
        if logger: logger.debug('(matching_handler, default): ' + repr((matching_handler, default)))
        return matching_handler or default


class resource_type(node):
    @staticmethod
    def construct_id(doc, original_base, wrapped_base, rest_uri):
        #type = U(doc.xml_select(u'//definition_list/item[term = "akara:type"]/defn'))
        if logger: logger.debug('Type: ' + repr(list(doc.xml_select(u'//*[@title="akara:metadata"]/gloss/label[.="akara:type"]/following-sibling::item[1]//@href'))))
        type = U(doc.xml_select(u'//*[@title="akara:metadata"]/gloss/label[.="akara:type"]/following-sibling::item[1]//@href'))
        wrapped_type, orig_type = wiki_uri(original_base, wrapped_base, type, rest_uri)
        if logger: logger.debug('Type URIs: ' + repr((type, wrapped_type, orig_type)))
        return wrapped_type

    def get_rulesheet(self):
        if self.rulesheet is None:
            #req = urllib2.Request(self.akara_type(), headers={'Accept': XML_IMT})
            #isrc = inputsource(req, resolver=self.resolver)
            if logger: logger.debug('akara type rest_uri: ' + self.rest_uri)
            isrc, resp = parse_moin_xml(self.rest_uri, resolver=self.resolver)
            doc = html.parse(isrc)
            rulesheet = U(doc.xml_select(u'//*[@title="akara:metadata"]/gloss/label[.="akara:rulesheet"]/following-sibling::item[1]//@href'))
            self.rulesheet = rulesheet or UNSPECIFIED
            if logger: logger.debug('RULESHEET: ' + rulesheet)
        return self.rulesheet
    
    def run_rulesheet(self, method='GET', accept='application/json'):
        if self.endpoint:
            #FIXME: This branch has not been tested since refactoring, and almost certainly does not work
            #FIXME: Just mobe to a subclass

            #(node_uri, node_type, endpoint, doc, metadata, original_wiki_base) = jsonizer
            #request = urllib2.Request(rest_uri, headers={'Accept': DOCBOOK_IMT})
            #body = opener.open(request).read()
            #logger.debug('rest_uri docbook body: ' + body[:200])
            query = urllib.urlencode({'node_uri': node_uri, 'node_type': node_type, 'original_wiki_base': original_wiki_base, 'original_wiki_link': link})
            #XXX this will lead to a re-parse of body/doc
            req = urllib2.Request(endpoint + '?' + query, self.body)
            output = opener.open(req).read()
            logger.debug('jsonizer result: ' + repr(rendered))
        else:
            #e.g. you can sign a rulesheet as follows:
            #python -c "import sys, hashlib; print hashlib.sha1('MYSECRET' + sys.stdin.read()).hexdigest()" < rsheet.py 
            #Make sure the rulesheet has not already been signed (i.e. does not have a hash on the first line)
            import hashlib
            rulesheet = self.get_rulesheet()
            rs = inputsource(rulesheet, resolver=self.resolver)
            token = rs.stream.readline().strip().lstrip('#')
            #logger.debug('Token: ' + repr((token, self.SECRET)))
            body = rs.stream.read()
            if token != hashlib.sha1(node.SECRET + body).hexdigest():
                raise RuntimeError('Security token verification failed')
            #chunks = []
            def U1(text): return U(text, noneok=True)
            #def write(text):
            #    chunks.append(text)

            handlers = {}
            #Decorator that allows the user to define request handler functions in rule sheets
            def handles(method, match=None):
                def deco(func):
                    handlers.setdefault(method, []).append((match, func))
                    return func
                return deco

            #env = {'write': write, 'resource': self, 'service': service, 'U': U1}
            resource_getter = partial(node.lookup, resolver=self.resolver)
            env = {'service': service, 'U': U1, 'handles': handles, 'R': resource_getter}

            #Execute the rule sheet
            exec body in env
            default = None
            matching_handler = None
            for (match, func) in handlers.get(method, []):
                if logger: logger.debug('(match, func): ' + repr((match, func)))
                if isinstance(match, basestring):
                    if match == accept:
                        matching_handler = func
                elif match is None:
                    default = func
                else:
                    if match(accept):
                        matching_handler = func
            if logger: logger.debug('(matching_handler, default): ' + repr((matching_handler, default)))
        return matching_handler or default


node.NODES[RESOURCE_TYPE_TYPE] = resource_type


from zenlib import SERVICES

def service(url, pymodule=None):
    '''
    e.g. service(u'http://example.org/your-service', pymodule="pypath.to.yourmodule")
    '''
    if pymodule:
        #Just importing the module should be enough if they're registering services properly
        mod = __import__(pymodule)
    return SERVICES[url]


#XXX: do we really need this function indirection for simple global dict assignment?
def register_node_type(type_id, nclass):
    node.NODES[type_id] = nclass

#

from zenlib import register_service

#Services for processing Moin pages
@zservice(u'http://purl.org/com/zepheira/zen/moinmodel/get-link-urls')
def get_link_urls(node):
    links = [ attr.xml_value for attr in node.xml_select(u'.//@href') ]
    return links


@zservice(u'http://purl.org/com/zepheira/zen/moinmodel/get-obj-urls')
def get_obj_urls(node):
    links = [ attr.xml_value for attr in node.xml_select(u'.//@src') ]
    return links


@zservice(u'http://purl.org/com/zepheira/zen/exhibit/jsonize')
def jsonize(obj):
    import simplejson
    return simplejson.dumps(obj)


def handle_list(node):
    return [ simple_struct(li) for li in node.li ]

def handle_gloss(node):
    return dict((U(l), simple_struct(first_item(l.xml_select(u'following-sibling::item'))))
                       for l in node.label)

def handle_subsection(node):
    return {U(node.title): simple_struct(node)}


structure_handlers = {
    u'ul': handle_list,
    u'p': U,
    u'gloss': handle_gloss,
    u's1': handle_subsection,
    u's2': handle_subsection,
    u's3': handle_subsection,
    u's4': handle_subsection,
    u's5': handle_subsection,
}


@zservice(u'http://purl.org/com/zepheira/zen/util/simple-struct')
def simple_struct(node):
    if len(node.xml_children) == 1 and not isinstance(node.xml_first_child, tree.element):
        return node.xml_first_child.xml_value
    top = []
    for child in node.xml_elements:
        handler = structure_handlers.get(child.xml_local, U)
        result = handler(child)
        if not isinstance(result, basestring) or result.strip():
            top.append(result)
    #logger.debug("simple_struct: " + repr(top))
    if len(top) == 1: top = top[0]
    return top


@zservice(u'http://purl.org/com/zepheira/zen/util/extract-liststrings')
def extract_liststrings(node):
    '''
    '''
    items = []
    l = node.xml_select(u'.//ul')
    if l:
        items = [ U(li).strip() for li in list(l[0].li) ]
    return items
