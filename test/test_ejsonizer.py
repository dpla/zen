import sys
import logging
from nose.tools import raises

from amara.thirdparty import json

from zen import ejsonify

#logging.basicConfig(level=logging.DEBUG)


def test_pull_ejson_by_patterns1():
    expected = [{'date': u'2009', 'format': u'audio'}, {'date': u'2007', 'format': u'audio'}, {'date': u'1997', 'format': u'language material -- serial'}]
    patterns = [(('docs',), {'date': ('dpla.date',), 'format': ('dpla.format', 0)})]
    items = ejsonify.pull_ejson_by_patterns(json.loads(DPLA_TEST), patterns)
    assert items == expected, items
    return


def test_pull_ejson_by_patterns2():
    patterns = [(('spam',), {'date': ('dpla.date',), 'format': ('dpla.format', 0)})]
    items = ejsonify.pull_ejson_by_patterns(json.loads(DPLA_TEST), patterns)
    assert items == [], items
    return


def test_pull_ejson_by_patterns3():
    expected = [{'date': u'2009', 'format': [u'audio', u'mp3'], 'creator': [u'Susan Jane Gilman']}, {'date': u'2007', 'format': [u'audio', u'mp3'], 'creator': [u'Linda Kulman']}, {'date': u'1997', 'format': u'language material -- serial', 'creator': [u"B'nai B'rith. Albert Einstein Lodge No. 5020"]}]
    patterns = [(('docs',), {'date': ('dpla.date',), 'format': ('dpla.format',), 'creator': ('dpla.creator',)})]
    items = ejsonify.pull_ejson_by_patterns(json.loads(DPLA_TEST), patterns)
    assert items == expected, items
    return


#Excerpted from http://jsonviewer.stack.hu/#http://api.dp.la/v0.03/item/?filter=dpla.keyword:einstein
DPLA_TEST = '''{
  "num_found": 4010,
  "start": "0",
  "limit": "25",
  "sort": "checkouts desc",
  "filter": "dpla.keyword:einstein",
  "docs": [
    {
      "dpla.date": "2009",
      "dpla.description": [
        "<em>Time and Again<\/em> spans time, finds mystery, delves into Science-Fiction, grounds itself in Einstein's theories and ultimately, settles into romance fantasy.  So what's the problem?  Author Susan Jane Gilman explains her guilty addiction to this cult pop thriller."
      ],
      "dpla.publisher": "National Public Radio",
      "dpla.format": [
        "audio",
        "mp3"
      ],
      "dpla.creator": [
        "Susan Jane Gilman"
      ],
      "dpla.title": "<em>Time and Again<\/em> spans time, delves into Science Fiction, and ultimately becomes romance fantasy.",
      "dpla.resource_type": "item",
      "dpla.id": "EF2485B2-0EF6-B47F-59EC-3F54E252AD79",
      "dpla.dataset_id": "npr_org_1312156800",
      "dpla.language": "English",
      "dpla.contributor": "npr_org",
      "dpla.contributor_record_id": "2636"
    },
    {
      "dpla.date": "2007",
      "dpla.description": [
        "It was Albert Einstein's tendency to rebel that was the source of his great creativity, says Walter Isaacson in a new bestseller. Einstein's real genius was his ability to focus on mundane things that most people overlook."
      ],
      "dpla.publisher": "National Public Radio",
      "dpla.format": [
        "audio",
        "mp3"
      ],
      "dpla.creator": [
        "Linda Kulman"
      ],
      "dpla.title": "A new biography argues that Einstein's tendency to rebel was the source of his creative genius.",
      "dpla.resource_type": "item",
      "dpla.id": "159920DE-B8FE-2626-7252-ACF35F34E044",
      "dpla.dataset_id": "npr_org_1312156800",
      "dpla.language": "English",
      "dpla.contributor": "npr_org",
      "dpla.contributor_record_id": "1360"
    },
    {
      "dpla.date": "1997",
      "245a": "Albert Einstein Lodge newsletter.",
      "dpla.creator": [
        "B'nai B'rith. Albert Einstein Lodge No. 5020"
      ],
      "dpla.id": "BB275112-5EFB-A228-0E2B-D4E62FCC5208",
      "dpla.language": "English",
      "9060": "MH",
      "dpla.contributor_record_id": "009416163",
      "988a": "20040722",
      "dpla.publisher": "B'nai B'rith, Albert Einstein Lodge No. 5020,",
      "dpla.title": "Albert Einstein Lodge newsletter",
      "dpla.resource_type": "item",
      "dpla.format": "language material -- serial",
      "260a": "Jerusalem :",
      "710b": "Albert Einstein Lodge No. 5020.",
      "dpla.dataset_id": "harvard_edu_1334336961",
      "260b": "B'nai B'rith, Albert Einstein Lodge No. 5020,",
      "dpla.contributor": "harvard_edu",
      "710a": "B'nai B'rith."
    }
  ],
  "facets": [
    
  ],
  "facet_queries": [
    
  ],
  "errors": [
    
  ]
}
'''



