# -*- coding: iso-8859-1 -*-
# 
"""

"""

class slaveinfo(object):
    SERVICEID = 'http://purl.org/xml3k/akara/services/demo/moinrest'
    def transformenv(environ):
        newenv = environ.copy()
        return newenv





import hashlib
import datetime
import urllib, urllib2
from gettext import gettext as _

from dateutil.parser import parse as dateparse

from functools import partial
from itertools import islice, dropwhile

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
from amara.lib.iri import split_uri_ref, split_fragment, relativize, absolutize, IriError, join, is_absolute
#from amara.bindery.model import examplotron_model, generate_metadata, metadata_dict
from amara.bindery.util import dispatcher, node_handler, property_sequence_getter
from amara.thirdparty import json, httplib2

from akara.util import copy_auth, find_peer_service
from akara.util.moin import wiki_uri, wiki_normalize, ORIG_BASE_HEADER, DOCBOOK_IMT, RDF_IMT, HTML_IMT, XML_IMT
from akara.services import simple_service

try:
    from akara import logger
except ImportError:
    logger = None

from zenlib.services import zservice, service_proxy

MOINREST_SERVICE_ID = 'http://purl.org/xml3k/akara/services/demo/moinrest'
FIRST_REQUEST_SEEN = False

#Following to be updated upon first request through Zen.  Used in zenuri_to_moinrest
MOINREST_BASEURI = None

#Following is updated on each request, to avoid possible reentrancy problems:
H = httplib2.Http('/tmp/.cache')

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


def zenuri_to_moinrest(environ, uri=None):
    #self_end_point = environ['SCRIPT_NAME'].rstrip('/') #$ServerPath/zen
    #self_end_point = request_uri(environ, include_query=False).rstrip('/')
    #self_end_point = guess_self_uri(environ)
    #absolutize(environ['SCRIPT_NAME'].rstrip('/'), request_uri(environ, include_query=False))
    #logger.debug('moinrest_uri: ' + repr((self_end_point, MOINREST_SERVICE_ID)))
    #logger.debug('zenuri_to_moinrest: ' + repr((moinresttop, environ['PATH_INFO'], environ['SCRIPT_NAME'])))
    if uri:
        if uri.startswith(MOINREST_BASEURI):
        #if moinresttop.split('/')[-1] == environ['SCRIPT_NAME'].strip('/'):
            #It is already a moin URL
            return uri or request_uri(environ)
        else:
            raise NotImplementedError('For now a Zen uri is required')
    else:
        moinrest_uri = join(MOINREST_BASEURI, environ['PATH_INFO'].lstrip('/'))
    #logger.debug('moinrest_uri: ' + repr(moinrest_uri))
    #logger.debug('moinrest_uri: ' + repr(MOINREST_BASEURI))
    return moinrest_uri


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

RESOURCE_TYPE_TYPE = u'http://purl.org/xml3k/akara/cms/resource-type'


UNSPECIFIED = object()

class node(object):
    '''
    Akara Moin/CMS node, a Moin wiki page that follows a template to direct workflow
    activity, including metadata extraction
    '''
    AKARA_TYPE = u'http://purl.org/xml3k/akara/cms/resource-type'
    NODES = {}
    ENDPOINTS = None

    @staticmethod
    def lookup(rest_uri, opener=None, environ={}, resolver=None):
        '''
        rest_uri - URI of the moinrest-wrapped version of the page
        opener - for specializing the HTTP request (e.g. to use auth)
        '''
        if not resolver:
            resolver = moinrest_resolver(opener=opener)
        if logger: logger.debug('node.lookup rest_uri: ' + rest_uri)
        isrc, resp = parse_moin_xml(rest_uri, H, resolver=resolver, environ=environ)
        if isrc is None:
            if logger: logger.debug("Error looking up resource: %d\n" % resp.status)
            return None

        doc = bindery.parse(isrc)
        #doc = bindery.parse(isrc, standalone=True, model=MOIN_DOCBOOK_MODEL)
        original_base, wrapped_base, original_page = resp[ORIG_BASE_HEADER].split()
        atype = resource_type.construct_id(doc, original_base, wrapped_base, rest_uri)
        if logger: logger.debug('node.lookup akara type: ' + repr(atype))
        #Older Moin CMS resource types are implemented by registration to the global node.NODES
        #Newer Moin CMS resource types are implemented by discovery of a URL,
        #to which a POST request executes the desired action
        cls = node.NODES.get(atype, node)
        instance = cls(doc, rest_uri, original_base, wrapped_base, akara_type=atype, resolver=resolver)
        return instance
        #return node.ENDPOINTS and (rest_uri, akara_type, node.ENDPOINTS[akara_type], doc, metadata, original_wiki_base)

    #FIXME: reconcile this with zen.py PUT handler
    @staticmethod
    def create(resource_type, body, ctype, opener=None, resolver=None):
        '''
        resource_type - type of the new resource to be created
        body - input information or document required to construct the resource page, according to the rule sheet
        '''
        from akara import request
        if not resolver:
            resolver = moinrest_resolver(opener=opener)
        resource_type = node.lookup(resource_type, resolver=resolver)
        handler = resource_type.run_rulesheet(request.environ, 'POST', ctype)
        url, wikified = handler(body)

        H.force_exception_to_status_code = False # set this explicitly since H is shared
        resp, content = H.request(url, "PUT", body=wikified, headers={'Content-Type' : 'text/plain'})

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
            if akara_type and isinstance(akara_type, basestring) and akara_type != RESOURCE_TYPE_TYPE:
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
        #logger.debug("section_titled: " + repr(title))
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
        #logger.debug("definition_list: " + repr(result))
        return result

    def definition_section(self, title, patterns=None):
        '''
        Helper to extract the first definition list from a named section
        '''
        return self.definition_list(u'.//gloss', contextnode=self.section(title), patterns=patterns)

    def get_proxy(self, environ, method, accept=None):
        return self.resource_type.run_rulesheet(environ, method, accept)

    def absolute_wrap(self, link):
        link = '/' + link.lstrip('/')
        #if logger: logger.debug('absolute_wrap: ' + repr((self.original_base, self.wrapped_base, link, self.rest_uri)))
        wrapped_link, orig_link = wiki_uri(self.original_base, self.wrapped_base, link, self.rest_uri)
        #if logger: logger.debug('absolute_wrap: ' + repr((link, wrapped_link, orig_link)))
        return wrapped_link


node.NODES[node.AKARA_TYPE] = node

def parse_moin_xml(uri, H, resolver=None, environ={}):
    #Stupid Moin XML export uses bogus nbsps, so this function encapsulates the kludge

    # Replaced urllib2 with httplib2 for the client cache, but we lose the custom
    # opener.  Luckily this function just uses GET which shouldn't require
    # Moin authentication most of the time.  FIXME
    H.force_exception_to_status_code = True
    headers={'Accept': XML_IMT}
    if 'HTTP_CACHE_CONTROL' in environ:
        # Propagate any cache-control request header received by Zen
        headers['cache-control'] = environ['HTTP_CACHE_CONTROL']

    resp,body = H.request(uri,"GET",headers=headers)

    if logger: logger.debug('parse_moin_xml (uri, fromcache): ' + repr((uri,resp.fromcache)))

    #logger.debug("parse_moin_xml: (resp,body) = " + repr((resp,body[:500])))
    if not str(resp.status).startswith('2'): return None, resp # fail gracefully if not found

    return inputsource(body, resolver=resolver), resp
    #return inputsource(body.replace('&nbsp;', '&#160;').replace('<p><p>', '<p></p>').replace('<p></s2>', '</s2>'), resolver=resolver), resp


class rulesheet(object):
    def __init__(self, source, rtype, resolver=None):
        '''
        '''
        #rs = inputsource(source, resolver=resolver)
        import cStringIO
        resp, body = H.request(source)
        stream = cStringIO.StringIO(body)
        self.token = stream.readline().strip().lstrip('#')
        #XXX In theory this is a microscopic security hole.  If someone could find a way
        #to open up an expliot by changing whitespace *in the middle of the line*
        #(wiki_normalize does not touch WS at the beginning of a line)
        #In practice, we accept this small risk
        self.body = wiki_normalize(stream.read())
        self.rtype = rtype
        return

    #
    def run(self, environ, method='GET', accept='application/json'):
        #e.g. you can sign a rulesheet as follows:
        #python -c "import sys, hashlib; print hashlib.sha1('MYSECRET' + sys.stdin.read()).hexdigest()" < rsheet.py 
        #Make sure the rulesheet has not already been signed (i.e. does not have a hash on the first line)
        rheet_sig = hashlib.sha1(node.SECRET + self.body).hexdigest()
        if self.token != rheet_sig:
            logger.debug("Computed signature: " + repr(rheet_sig))
            raise RuntimeError('Security token verification failed')
        #chunks = []
        #U1 is just a smarter variant of the "Unicode, dammit!"
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
                # Set appropriate default media type when no match is specified in @handles
                if match is None :
                    func.imt = 'application/json'
                else :
                    func.imt = match
                handlers.setdefault(method, []).append((match, func))
                return func
            return deco

        #env = {'write': write, 'resource': self, 'service': service, 'U': U1}
        resource_getter = partial(node.lookup, resolver=self.rtype.resolver)
        env = {'service': service_proxy, 'U': U1, 'handles': handles, 'R': resource_getter,
                'use': use, 'environ': environ, 'logger': logger, 'H': H}

        #Execute the rule sheet
        exec self.body in env
        default = None
        matching_handler = None
        for (match, func) in handlers.get(method, []):
            if logger: logger.debug('(match, func), method : ' + repr((match, func)) + "," + method )
            if isinstance(match, basestring):
                if match == accept:
                    matching_handler = func
            elif (match is None):
                default = func
            else:
                if match(accept):
                    matching_handler = func
        if logger: logger.debug('(matching_handler, default): ' + repr((matching_handler, default)))
        return matching_handler or default


TYPE_PATTERN = u'//*[@title="akara:metadata"]/gloss/label[.="akara:type"]/following-sibling::item[1]//jump/@url'
RULESHEET_LINK_PATTERN = u'//*[@title="akara:metadata"]/gloss/label[.="akara:rulesheet"]/following-sibling::item[1]//jump/@url'
RULESHEET_ATT_PATTERN = u'//*[@title="akara:metadata"]/gloss/label[.="akara:rulesheet"]/following-sibling::item[1]//attachment/@href'


class resource_type(node):
    @staticmethod
    def construct_id(doc, original_base, wrapped_base, rest_uri):
        #TYPE_PATTERN = u'//*[@title="akara:metadata"]/gloss/label[.="akara:type"]/following-sibling::item[1]//@href'
        #TYPE_PATTERN = u'//*[@title="akara:metadata"]/following-sibling::gloss/label[.="akara:type"]/following-sibling::item[1]//jump'
        #type = U(doc.xml_select(u'//definition_list/item[term = "akara:type"]/defn'))
        type = U(doc.xml_select(TYPE_PATTERN))
        if logger: logger.debug('resource_type.construct_id type: ' + repr(type))
        if not type: return None
        wrapped_type, orig_type = wiki_uri(original_base, wrapped_base, type, rest_uri, raw=True)
        if logger: logger.debug('resource_type.construct_id wiki_uri trace: ' + repr((wrapped_type, orig_type, original_base, wrapped_base, rest_uri)))
        return wrapped_type or type

    def get_rulesheet(self):
        if self.rulesheet is None:
            #req = urllib2.Request(self.akara_type(), headers={'Accept': XML_IMT})
            #isrc = inputsource(req, resolver=self.resolver)
            isrc, resp = parse_moin_xml(self.rest_uri, H, resolver=self.resolver)
            doc = bindery.parse(isrc)
            rulesheet_link = U(doc.xml_select(RULESHEET_LINK_PATTERN))
            if rulesheet_link and not is_absolute(rulesheet_link):
                wrapped, orig = wiki_uri(self.original_base, self.wrapped_base, rulesheet_link, self.rest_uri)
                self.rulesheet = wrapped
            elif rulesheet_link:
                self.rulesheet = rulesheet_link
            else:
                rulesheet_att = U(doc.xml_select(RULESHEET_ATT_PATTERN))
                if rulesheet_att:
                    self.rulesheet = self.rest_uri + u';attachment=' + rulesheet_att
                else:
                    self.rulesheet = UNSPECIFIED

            if logger: logger.debug('resource_type.get_rulesheet rest_uri, rulesheet: ' + repr((self.rest_uri, self.rulesheet)))
        return self.rulesheet
    
    def run_rulesheet(self, environ, method='GET', accept='application/json'):
        #FIXME: Deprecate
        return rulesheet(self.get_rulesheet(), self, resolver=self.resolver).run(environ, method, accept)


node.NODES[RESOURCE_TYPE_TYPE] = resource_type


from zenlib.services import SERVICES

def use(pymodule):
    '''
    e.g. use("pypath.to.yourmodule")
    '''
    #Just importing the module should be enough if they're registering services properly
    try:
        mod = __import__(pymodule)
    except ImportError as e:
        logger.debug('Unable to import declared module, so associated services will have to be available through discovery: ' + repr(e))
    return


#XXX: do we really need this function indirection for simple global dict assignment?
def register_node_type(type_id, nclass):
    node.NODES[type_id] = nclass

#

def curation_ingest(rest_uri, mointext, user, H, auth_headers):
    '''
    '''
    import diff_match_patch
    from akara.util.moin import HISTORY_MODEL

    resp, content = H.request(rest_uri + ';history', "GET", headers=auth_headers)
    historydoc = bindery.parse(content, model=HISTORY_MODEL)
    rev = first_item(dropwhile(lambda rev: unicode(rev.editor) != user, (historydoc.history.rev or [])))
    if not rev or historydoc.history.rev.editor == user:
        #New record, or the most recent modification is also by the akara user
        logger.debug('Direct update (no conflict scenario)')
        return mointext
    else:
        #Potential conflict
        logger.debug('Potential conflict scenario')
        resp, curr_akara_rev = H.request(rest_uri + '?rev=' + rev.id, "GET", headers=auth_headers)
        curr_akara_rev = curation_ingest.wiki_normalize(curr_akara_rev)
        dmp = diff_match_patch.diff_match_patch()
        patches = dmp.patch_make(curr_akara_rev, mointext)
        logger.debug('PATCHES: ' + dmp.patch_toText(patches))
        diff_match_patch.patch_fixup(patches) #Uche's hack-around for an apparent bug in diff_match_patch
        logger.debug('PATCHES: ' + dmp.patch_toText(patches))
        #XXX Possible race condition.  Should probably figure out a way to get all revs atomically
        resp, present_rev = H.request(rest_uri, "GET", headers=auth_headers)
        present_rev = curation_ingest.wiki_normalize(present_rev)
        patched, flags = dmp.patch_apply(patches, present_rev)
        logger.debug('PATCH RESULTS: ' + repr((flags)))
        if all(flags):
            #Patch can be completely automated
            return patched
        else:
            #At least one patch hunk failed
            logger.debug('CONFLICT: ' + repr(flags))
            return None
    return


DIFF_CMD = 'diff -u'
PATCH_CMD = 'patch -p0'

def curation_ingest_via_subprocess(rest_uri, mointext, prior_ingested, user, H, auth_headers):
    '''
    Support function for freemix services.  Inital processing to guess media type of post body.
    '''
    import os
    import tempfile
    from subprocess import Popen, PIPE

    prior_rev, zen_rev, curated_rev = curation_ingest_versions(rest_uri, user, H, auth_headers)
    if not curated_rev:
        #If there has never been a curated rev, we don't have to be on guard for conflicts
        logger.debug('Direct update (no conflict scenario)')
        return True, mointext
    else:
        #Potential conflict
        logger.debug('Potential conflict scenario')
        #We need to diff the latest ingest *candidate* (i.e. mointext) version against the prior ingest *candidate* version

        oldwiki = tempfile.mkstemp(suffix=".txt")
        newwiki = tempfile.mkstemp(suffix=".txt")
        os.write(oldwiki[0], prior_ingested)
        os.write(newwiki[0], mointext)
        #os.fsync(oldwiki[0]) #is this needed with the close below?
        os.close(oldwiki[0])
        os.close(newwiki[0])

        cmdline = ' '.join([DIFF_CMD, oldwiki[1], newwiki[1]])
        logger.debug('cmdline1: \n' + cmdline)
        process = Popen(cmdline, stdout=PIPE, shell=True)
        patch = process.stdout.read()

        logger.debug('PATCHES: \n' + patch)
        #XXX Possible race condition.  Should probably figure out a way to get all revs atomically
        resp, present_rev = H.request(rest_uri, "GET", headers=auth_headers)
        present_rev = curation_ingest.wiki_normalize(present_rev)

        currwiki = tempfile.mkstemp(suffix=".txt")
        os.write(currwiki[0], present_rev)
        #os.fsync(currwiki[0]) #is this needed with the close below?
        os.close(currwiki[0])

        cmdline = ' '.join([PATCH_CMD, currwiki[1]])
        logger.debug('cmdline1: \n' + cmdline)
        process = Popen(cmdline, stdin=PIPE, stdout=PIPE, shell=True)
        process.stdin.write(patch)
        process.stdin.close()
        cmdoutput = process.stdout.read()

        #Apparently process.returncode isn't a useful indicator of patch rejection
        conflict = 'FAILED' in cmdoutput and 'rejects' in cmdoutput

        logger.debug('PATCH COMMAND OUTPUT: ' + repr((cmdoutput)))
        patched = open(currwiki[1]).read()
        patched = curation_ingest.wiki_normalize(patched)
        
        logger.debug('PATCH RESULTS: ' + repr((patched)))
        
        logger.debug('RETURN CODE: ' + repr((process.returncode)))
        process.returncode
        
        if conflict:
            #At least one patch hunk failed
            #logger.debug('CONFLICT: ' + repr(process.returncode))
            return False, patch
        else:
            #Patch can be completely automated
            return True, patched
    return False, none


curation_ingest = curation_ingest_via_subprocess
#By default, normalize for curator ops using standard Akara wiki normalization
curation_ingest.wiki_normalize = wiki_normalize

def curation_ingest_versions(rest_uri, user, H, auth_headers):
    from akara.util.moin import HISTORY_MODEL
    resp, content = H.request(rest_uri + ';history', "GET", headers=auth_headers)
    historydoc = bindery.parse(content, model=HISTORY_MODEL)
    try:
        prior_rev = historydoc.history.rev[1]
    except:
        prior_rev = None
    try:
        zen_rev = first_item(dropwhile(lambda rev: unicode(rev.editor) != user, (historydoc.history.rev or [])))
    except AttributeError: #'entity_base' object has no attribute 'history'
        zen_rev = None
    try:
        curated_rev = first_item(dropwhile(lambda rev: unicode(rev.editor) == user, (historydoc.history.rev or [])))
    except AttributeError: #'entity_base' object has no attribute 'history'
        curated_rev = None
    #if not rev or historydoc.history.rev.editor == user: #New record, or the most recent modification is also by the akara user
    logger.debug('curation_ingest_versions: rest_uri, curr_rev, zen_rev, curated_rev: ' +
        repr((rest_uri, (prior_rev.xml_encode() if prior_rev else None, zen_rev.xml_encode() if zen_rev else None, curated_rev.xml_encode() if curated_rev else None))))
    return prior_rev, zen_rev, curated_rev


from zenlib.services import register_service

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
    return json.dumps(obj)

# Remove null(aka None) valued properties from a dictionary
@zservice(u'http://purl.org/com/zepheira/zen/exhibit/strip-null')
def strip_null(obj):
    return dict( (n,v) for (n,v) in obj.iteritems() if v)

def handle_list(node):
    return [ simple_struct(li) for li in node.li ]

def handle_gloss(node):
    return dict((U(l), simple_struct(first_item(l.xml_select(u'following-sibling::item'))))
                       for l in node.label)

def handle_subsection(node):
    return (U(node.title), simple_struct(node))


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

def handle_lone_para(node):
    #See: http://foundry.zepheira.com/issues/788
    pstringval = node.xml_select(u'string(p[1])')
    if node.xml_select(u'string(.)').strip() == pstringval.strip():
        return U(pstringval)
    return None


@zservice(u'http://purl.org/com/zepheira/zen/util/simple-struct')
def simple_struct(node):
    '''
    >>> from amara.bindery import parse
    >>> from zenlib.moinmodel import simple_struct
    >>> X = '<s2 id="XYZ" title="XYZ"><p>Hello</p></s2>'
    >>> doc = parse(X)
    >>> simple_struct(doc)
    [(u'XYZ', [(u'A', [u'Hello', (u'AB', [u'World'])])])]

    >>> X = '<s2 id="XYZ" title="XYZ"><p/><s3 id="A" title="A"><p>Hello</p><s4 id="AB" title="AB"><p>World</p></s4></s3></s2>'
    >>> doc = parse(X)
    >>> simple_struct(doc)
    [(u'XYZ', [(u'A', [u'Hello', (u'AB', [u'World'])])])]

    >>> X = '<s2 id="XYZ" title="XYZ"><p/><s3 id="A" title="A"><p>Hello</p><s4 id="AB" title="AB"><gloss><label>spam</label><item>eggs</item></gloss></s4></s3></s2>'
    >>> doc = parse(X)
    >>> simple_struct(doc)
    [(u'XYZ', [(u'A', [u'Hello', (u'AB', [{u'spam': u'eggs'}])])])]

    >>> X = '<s1 id="XYZ" title="XYZ"><s2 id="1" title="1"><ul><li><p>WikiLink </p></li></ul><p/></s2><s2 id="1" title="1"><ul><li>Wikilink </li></ul><p/></s2></s1>'
    >>> doc = parse(X)
    >>> simple_struct(doc)
    [(u'XYZ', [(u'1', [[u'WikiLink ']]), (u'1', [[u'Wikilink ']])])]
    '''
    #To test the above: python -m doctest lib/moinmodel.py
    #FIXME: integrate into test/test_moinmodel_services.py
    
    if not node: return None
    if len(node.xml_children) == 1 and not isinstance(node.xml_first_child, tree.element):
        return node.xml_first_child.xml_value
    simple_pstringval = handle_lone_para(node)
    if simple_pstringval is not None: return simple_pstringval
    top = []
    for child in node.xml_elements:
        handler = structure_handlers.get(child.xml_local, U)
        result = handler(child)
        if not isinstance(result, basestring) or result.strip():
            top.append(result)
    #logger.debug("simple_struct: " + repr(top))
    #if len(top) == 1: top = top[0]
    return top


@zservice(u'http://purl.org/com/zepheira/zen/util/extract-liststrings')
def extract_liststrings(node):
    '''
    Helper to extract all list items from a section
    '''
    items = []
    l = node.xml_select(u'.//ul')
    if l:
        items = [ U(li).strip() for li in list(l[0].li) ]
    return items


@zservice(u'http://purl.org/com/zepheira/zen/util/get-child-pages')
def get_child_pages(node, limit=None):
    '''
    node - the node for the page to be processed
    limit - return no more than this many pages
    
    >>> from zenlib.moinmodel import node, get_child_pages
    >>> p = node.lookup(u'http://localhost:8880/moin/x/poetpaedia/poet')
    >>> print get_child_pages(p)
    [u'http://localhost:8880/moin/x/poetpaedia/poet/epound', u'http://localhost:8880/moin/x/poetpaedia/poet/splath']
    
    '''
    #isrc, resp = parse_moin_xml(node.rest_uri, resolver=node.resolver)
    #hrefs = node.doc.xml_select(u'//h:table[@class="navigation"]//@href', prefixes={u'h': u'http://www.w3.org/1999/xhtml'})
    #For some reason some use XHTML NS and some don't
    #if not hrefs:
    #    hrefs = node.doc.xml_select(u'//table[@class="navigation"]//@href')

    hrefs = node.doc.xml_select(u'//*[@class="navigation"]//@href')
    if limit:
        hrefs = islice(hrefs, 0, int(limit))
    hrefs = list(hrefs); #logger.debug('get_child_pages HREFS1: ' + repr(hrefs))
    hrefs = [ wiki_uri(node.original_base, node.wrapped_base, navchild.xml_value, node.rest_uri, raw=True)[0] for navchild in hrefs ]
    return hrefs
