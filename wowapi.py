# -*- coding: utf-8 -*-

#!/usr/bin/env python

import json,time

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.ext import ndb

class APIKey(ndb.Model):
    key = ndb.StringProperty(indexed=True,required=True)

class ClassEntry(ndb.Model):
    classId = ndb.IntegerProperty()
    mask = ndb.IntegerProperty()
    powerType = ndb.StringProperty()
    name = ndb.StringProperty()

class Realm(ndb.Model):
    realm = ndb.StringProperty(indexed=True,required=True)
    slug = ndb.StringProperty(indexed=True,required=True)

class Importer:
    def load(self, realm, frealm, toonlist, data, groupstats):
        q = APIKey.query()
        apikey = q.fetch()[0]

        q = ClassEntry.query()
        res = q.fetch()

        classes = dict()
        for c in res:
            classes[c.classId] = c.name

        # Request all of the toon data from the blizzard API and determine the
        # group's ilvls, armor type counts and token type counts.  subs are not
        # included in the counts, since they're not really part of the main
        # group.
        for toon in toonlist:
            toonname = toon.name
            toonrealm = toon.realm
            if (toonrealm == realm):
                toonfrealm = frealm
            else:
                rq2 = Realm.query(
                    Realm.slug == toonrealm, namespace='Realms')
                rq2res = rq2.fetch()
                toonfrealm = rq2res[0].realm
            
            # TODO: this object can probably be a class instead of another dict
            newdata = dict()
            data.append(newdata)

            # a realm is received in the json data from the API, but we need to
            # pass the normalized value to the next stages.  ignore this field
            # from the data.
            newdata['toonrealm'] = toonrealm
            newdata['toonfrealm'] = toonfrealm
            newdata['main'] = toon.main
            newdata['role'] = toon.role

            url = 'https://us.api.battle.net/wow/character/%s/%s?fields=items,guild&locale=en_US&apikey=%s' % (toonrealm, toonname, apikey.key)
            # create the rpc object for the fetch method.  the deadline
            # defaults to 5 seconds, but that seems to be too short for the
            # Blizzard API site sometimes.  setting it to 10 helps a little
            # but it makes page loads a little slower.
            rpc = urlfetch.create_rpc(10)
            rpc.callback = self.create_callback(rpc, toonname, newdata, groupstats, classes)
            urlfetch.make_fetch_call(rpc, url)
            newdata['rpc'] = rpc

            # The Blizzard API has a limit of 10 calls per second.  Sleep here
            # for a very brief time to avoid hitting that limit.
            time.sleep(0.1)

        # Now that all of the RPC calls have been created, loop through the data
        # dictionary one more time and wait for each fetch to be completed. Once
        # all of the waits finish, then we have all of the data from the
        # Blizzard API and can loop through all of it and build the page.
        start = time.time()
        for d in data:
            d['rpc'].wait()
        end = time.time()
        print "Time spent retrieving data: %f seconds" % (end-start)

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, rpc, name, toondata, groupstats, classes):

        try:
            response = rpc.get_result()
        except urlfetch_errors.DeadlineExceededError:
            print('urlfetch threw DeadlineExceededError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Timeout retrieving data from Battle.net for %s.  Refresh page to try again.' % name
            return
        except urlfetch_errors.DownloadError:
            print('urlfetch threw DownloadError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Network error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return
        except:
            print('urlfetch threw unknown exception on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Unknown error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return

        # change the json from the response into a dict of data and store it
        # into the toondata object that was passed in.
        jsondata = json.loads(response.content)
        toondata.update(jsondata);

        # Blizzard's API will return an error if it couldn't retrieve the data
        # for some reason.  Check for this and log it if it fails.  Note that
        # this response doesn't contain the toon's name so it has to be added
        # in afterwards.
        if 'status' in jsondata and jsondata['status'] == 'nok':
            print('Blizzard API failed to find toon %s for reason: %s' %
                  (name.encode('ascii','ignore'), jsondata['reason']))
            toondata['toon'] = name
            toondata['reason'] = "Error retrieving data for %s from Blizzard API: %s" % (name, jsondata['reason'])
            return

        print "got good results for %s" % name.encode('ascii','ignore')

        # For each toon, update the statistics for the group as a whole
        if toondata['main'] == True:
            groupstats.ilvlmains += 1
            groupstats.totalilvl += jsondata['items']['averageItemLevel']
            groupstats.totalilvleq += jsondata['items']['averageItemLevelEquipped']

            toonclass = classes[jsondata['class']]
            if toonclass in ['Paladin','Warrior','Death Knight']:
                groupstats.plate += 1
            elif toonclass in ['Mage','Priest','Warlock']:
                groupstats.cloth += 1
            elif toonclass in ['Druid','Monk','Rogue']:
                groupstats.leather += 1
            elif toonclass in ['Hunter','Shaman']:
                groupstats.mail += 1

            if toonclass in ['Paladin','Priest','Warlock']:
                groupstats.conq += 1
            elif toonclass in ['Warrior','Hunter','Shaman','Monk']:
                groupstats.prot += 1
            elif toonclass in ['Death Knight','Druid','Mage','Rogue']:
                groupstats.vanq += 1

    def create_callback(self, rpc, name, toondata, groupstats, classes):
        return lambda: self.handle_result(rpc, name, toondata, groupstats, classes)