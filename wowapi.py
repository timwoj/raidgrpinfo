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
            rpc.callback = self.create_callback(rpc, toonname, newdata,
                                                groupstats, classes)
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

        # Because Blizzard continues to fail to update the ilvls of items from
        # BRF to match the ilvl boost they gave them, I'm updating them manually
        # here.  This sucks and is a hack, but it's necessary to make the display
        # correct.  Whenever Blizzard fixes their shit, this can be removed.
        itemcount = 0
        totalilvl = 0
        items = toondata['items']
        for kind in ['head','shoulder','chest','hands','legs','feet','neck','back','wrist','waist','feet','finger1','finger2','trinket1','trinket2','mainHand','offHand']:
            if kind in items:
                if ((items[kind]['context'] == 'raid-finder' and
                     (items[kind]['itemLevel'] == 660 or
                      items[kind]['itemLevel'] == 666 or
                      items[kind]['itemLevel'] == 650 or
                      items[kind]['itemLevel'] == 655)) or
                    (items[kind]['context'] == 'raid-normal' and
                     (items[kind]['itemLevel'] == 665 or
                      items[kind]['itemLevel'] == 671)) or
                    (items[kind]['context'] == 'raid-heroic' and
                     (items[kind]['itemLevel'] == 680 or
                      items[kind]['itemLevel'] == 686)) or
                    (items[kind]['context'] == 'raid-mythic' and
                     (items[kind]['itemLevel'] == 695 or
                      items[kind]['itemLevel'] == 701))):
                    items[kind]['itemLevel'] += 5
                totalilvl += items[kind]['itemLevel']
                itemcount += 1

        toondata['items']['averageItemLevelEquipped'] = (int)(totalilvl / itemcount)

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

class Setup:
    # Loads the list of realms into the datastore from the blizzard API so that
    # the realm list on the front page gets populated.  Also loads the list of
    # classes into a table on the DB so that we don't have to request it 
    def initdb(self):

        q = APIKey.query()
        apikey = q.fetch()[0]

        # Delete all of the entities out of the realm datastore so fresh entities
        # can be loaded.
        q = Realm.query()
        for r in q.fetch():
            r.key.delete()

        # retrieve a list of realms from the blizzard API
        url = 'https://us.api.battle.net/wow/realm/status?locale=en_US&apikey=%s' % apikey.key
        response = urlfetch.fetch(url)
        jsondata = json.loads(response.content)

        for realm in jsondata['realms']:
            r = Realm(realm=realm['name'], slug=realm['slug'],
                      namespace='Realms', id=realm['slug'])
            r.put()

        # Delete all of the entities out of the class datastore so fresh entities
        # can be loaded.
        q = ClassEntry.query()
        for r in q.fetch():
            r.key.delete()

        # retrieve a list of classes from the blizzard API
        url = 'https://us.api.battle.net/wow/data/character/classes?locale=en_US&apikey=%s' % apikey.key
        response = urlfetch.fetch(url)
        rawclasses = json.loads(response.content)
        for c in rawclasses['classes']:
            ce = ClassEntry(classId=c['id'], mask=c['mask'],
                            powerType=c['powerType'], name=c['name'])
            ce.put();

        return [len(jsondata['realms']), len(rawclasses['classes'])]

    # The new Battle.net Mashery API requires an API key when using it.  This
    # method stores an API in the datastore so it can used in later page requests.
    def setkey(self,apikey):

        # Delete all of the entities out of the apikey datastore so fresh entities
        # can be loaded.
        q = APIKey.query()
        result = q.fetch();
        if (len(result) == 0):
            k = APIKey(key = apikey)
            k.put()
        else:
            k = result[0]
            k.key = apikey
            k.put()
