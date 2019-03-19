# -*- coding: utf-8 -*-

#!/usr/bin/env python

import json
import time
import os
import base64
import urllib
import sys

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.ext import ndb
from google.appengine.api import memcache

def get_oauth_headers():
    oauth_token = memcache.get('oauth_bearer_token')
    if oauth_token is None:
        path = os.path.join(os.path.split(__file__)[0], 'api-auth.json')
        authdata = json.load(open(path))

        credentials = "{}:{}".format(authdata['blizzard_client_id'], authdata['blizzard_client_secret'])
        encoded_credentials = base64.b64encode(credentials)

        response = urlfetch.fetch('https://us.battle.net/oauth/token',
                                  payload='grant_type=client_credentials',
                                  method=urlfetch.POST,
                                  headers={'Authorization': 'Basic ' + encoded_credentials})

        if response.status_code == urlfetch.httplib.OK:
            response_data = json.loads(response.content)
            oauth_token = response_data['access_token']

            # Blizzard sends an expiration time for the token in the response,
            # but we want to make sure that our memcache expires before they
            # do. Subtract 60s off that so we make sure to re-request before
            # it's expired.
            expiration = int(response_data['expires_in']) - 60
            memcache.set('oauth_bearer_token', oauth_token, time=expiration)

    if oauth_token is None:
        return {}
    else:
        return {'Authorization': 'Bearer ' + oauth_token}

class ClassEntry(ndb.Model):
    classId = ndb.IntegerProperty()
    mask = ndb.IntegerProperty()
    powerType = ndb.StringProperty()
    name = ndb.StringProperty()

class Realm(ndb.Model):
    realm = ndb.StringProperty(indexed=True, required=True)
    slug = ndb.StringProperty(indexed=True, required=True)

class Importer:
    # These are the "Better" enchants used for quality checking on enchants
    ENCHANTS = {
        'finger1': [5942, 5943, 5944, 5945],
        'finger2': [5942, 5943, 5944, 5945],
        'mainHand': [5946, 5948, 5949, 5950, 5957, 5962, 5963, 5964, 5965, 5966, 3847, 3368, 3370],
        'offHand': [5946, 5948, 5949, 5950, 5957, 5962, 5963, 5964, 5965, 5966, 3847, 3368, 3370],
    }

    def load(self, realm, frealm, toonlist, data, groupstats):
        path = os.path.join(os.path.split(__file__)[0], 'api-auth.json')
        authdata = json.load(open(path))

        query = ClassEntry.query()
        result = query.fetch()

        classes = dict()
        for cls in result:
            classes[cls.classId] = cls.name

        oauth_headers = get_oauth_headers()

        # Request all of the toon data from the blizzard API and determine the
        # group's ilvls, armor type counts and token type counts.  subs are not
        # included in the counts, since they're not really part of the main
        # group. The Blizzard API has a limit of 100 calls per second. Keep a
        # count and if we hit 100 calls, we'll wait a half second before
        # continuing. If someone has more than 100 toons in their list, they
        # should be slapped.
        toon_count = 0
        for toon in toonlist:
            toonname = toon.name
            toonrealm = toon.realm
            if toonrealm == realm:
                toonfrealm = frealm
            else:
                rq2 = Realm.query(Realm.slug == toonrealm, namespace='Realms')
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
            newdata['status'] = toon.status
            newdata['role'] = toon.role

            url = 'https://us.api.blizzard.com/wow/character/%s/%s?fields=items,guild&locale=en_US' % (toonrealm, urllib.quote(toonname.encode('utf-8')))

            # create the rpc object for the fetch method.  the deadline
            # defaults to 5 seconds, but that seems to be too short for the
            # Blizzard API site sometimes.  setting it to 10 helps a little
            # but it makes page loads a little slower.
            rpc = urlfetch.create_rpc(10)
            rpc.callback = self.create_callback(rpc, toonname, newdata, groupstats, classes)
            urlfetch.make_fetch_call(rpc, url, headers=oauth_headers)
            newdata['rpc'] = rpc

            toon_count = toon_count + 1
            if toon_count > 100:
                time.sleep(0.5)
                toon_count = 0

        # Now that all of the RPC calls have been created, loop through the data
        # dictionary one more time and wait for each fetch to be completed. Once
        # all of the waits finish, then we have all of the data from the
        # Blizzard API and can loop through all of it and build the page.
        start = time.time()
        for entry in data:
            entry['rpc'].wait()
        end = time.time()
        print("Time spent retrieving data: %f seconds" % (end-start))

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, rpc, name, toondata, groupstats, classes):

        try:
            response = rpc.get_result()
        except urlfetch_errors.DeadlineExceededError:
            print('urlfetch threw DeadlineExceededError on toon %s' % name.encode('ascii', 'ignore'))
            toondata['name'] = name
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Timeout retrieving data from Battle.net for %s.  Refresh page to try again.' % name
            return
        except urlfetch_errors.DownloadError:
            print('urlfetch threw DownloadError on toon %s' % name.encode('ascii', 'ignore'))
            toondata['name'] = name
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Network error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return
        except:
            print('urlfetch threw unknown exception on toon %s' % name.encode('ascii', 'ignore'))
            toondata['name'] = name
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Unknown error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return

        # Catch HTTP errors from Blizzard. 404s really wreck everything.
        if response.status_code != 200:
            print('urlfetch returned a %d status code on toon %s' % (response.status_code, name.encode('ascii', 'ignore')))
            toondata['name'] = name
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Got a %d from Battle.net for toon %s.  Refresh page to try again.' % (response.status_code, name)
            return

        # change the json from the response into a dict of data and store it
        # into the toondata object that was passed in.
        jsondata = json.loads(response.content)
        toondata.update(jsondata)

        # Blizzard's API will return an error if it couldn't retrieve the data
        # for some reason.  Check for this and log it if it fails.  Note that
        # this response doesn't contain the toon's name so it has to be added
        # in afterwards.
        if 'load_status' in jsondata and jsondata['load_status'] == 'nok':
            print('Blizzard API failed to find toon %s for reason: %s' %
                  (name.encode('ascii', 'ignore'), jsondata['reason']))
            toondata['name'] = name
            toondata['reason'] = "Error retrieving data for %s from Blizzard API: %s" % (name, jsondata['reason'])
            return

        print "got good results for %s" % name.encode('ascii', 'ignore')

        # For each toon, update the statistics for the group as a whole
        if toondata['status'] == 'main':
            groupstats.ilvlmains += 1
            groupstats.totalilvl += jsondata['items']['averageItemLevel']
            groupstats.totalilvleq += jsondata['items']['averageItemLevelEquipped']

            toonclass = classes[jsondata['class']]
            if toonclass in ['Paladin', 'Warrior', 'Death Knight']:
                groupstats.plate += 1
            elif toonclass in ['Mage', 'Priest', 'Warlock']:
                groupstats.cloth += 1
            elif toonclass in ['Druid', 'Monk', 'Rogue', 'Demon Hunter']:
                groupstats.leather += 1
            elif toonclass in ['Hunter', 'Shaman']:
                groupstats.mail += 1

        # Group all gems together into a comma-separated list for tooltipParams
        for slot in toondata['items']:
            if not isinstance(toondata['items'][slot], dict):
                continue
            item = toondata['items'][slot]
            if 'tooltipParams' in item:
                gem0 = 0
                gem1 = 0
                gem2 = 0
                if 'gem0' in item['tooltipParams']:
                    gem0 = item['tooltipParams']['gem0']
                    del item['tooltipParams']['gem0']
                if 'gem1' in item['tooltipParams']:
                    gem1 = item['tooltipParams']['gem1']
                    del item['tooltipParams']['gem1']
                if 'gem2' in item['tooltipParams']:
                    gem2 = item['tooltipParams']['gem2']
                    del item['tooltipParams']['gem2']
                if gem0 != 0 or gem1 != 0 or gem2 != 0:
                    item['tooltipParams']['gems'] = ':'.join(str(x) for x in [gem0, gem1, gem2])

            # Default enchant checking to -1 for all items
            item['enchant'] = -1

            if slot in Importer.ENCHANTS:
                if slot != 'offHand' or 'weaponInfo' in item:
                    enchant = item.get('tooltipParams', {}).get('enchant', 0)
                    if enchant in Importer.ENCHANTS[slot]:
                        item['enchant'] = 2
                    elif enchant != 0:
                        item['enchant'] = 1
                    else:
                        item['enchant'] = 0

            item['azeriteLevel'] = item.get('azeriteItem', {}).get('azeriteLevel', 0)

    def create_callback(self, rpc, name, toondata, groupstats, classes):
        return lambda: self.handle_result(rpc, name, toondata, groupstats, classes)

class Setup:
    # Loads the list of realms into the datastore from the blizzard API so that
    # the realm list on the front page gets populated.  Also loads the list of
    # classes into a table on the DB so that we don't have to request it
    def initdb(self, app):
        try:
            oauth_headers = get_oauth_headers()
            realmcount = self.init_realms(oauth_headers)
            classcount = self.init_classes(oauth_headers)
            return [realmcount, classcount]
        except:
            app.logger.error("Error:", sys.exc_info()[0])
            return [0, 0]

    def init_realms(self, oauth_headers):
        # Delete all of the entities out of the realm datastore so fresh
        # entities can be loaded.
        query = Realm.query()
        for row in query.fetch():
            row.key.delete()

        # retrieve a list of realms from the blizzard API
        url = 'https://us.api.blizzard.com/wow/realm/status?locale=en_US'
        response = urlfetch.fetch(url, headers=oauth_headers)
        if response.status_code == 200:
            jsondata = json.loads(response.content)
        else:
            jsondata = {'realms': []}

        for realm in jsondata['realms']:
            new_realm = Realm(realm=realm['name'], slug=realm['slug'],
                              namespace='Realms', id=realm['slug'])
            new_realm.put()

        return len(jsondata['realms'])

    def init_classes(self, oauth_headers):
        # Delete all of the entities out of the class datastore so fresh
        # entities can be loaded.
        query = ClassEntry.query()
        for row in query.fetch():
            row.key.delete()

        # retrieve a list of classes from the blizzard API
        url = 'https://us.api.blizzard.com/wow/data/character/classes?locale=en_US'
        response = urlfetch.fetch(url, headers=oauth_headers)
        if response.status_code == 200:
            jsondata = json.loads(response.content)
        else:
            jsondata = {'classes': []}

        for cls in jsondata['classes']:
            class_entry = ClassEntry(classId=cls['id'], mask=cls['mask'],
                                     powerType=cls['powerType'], name=cls['name'])
            class_entry.put()

        return len(jsondata['classes'])
