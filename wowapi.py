# -*- coding: utf-8 -*-
#!/usr/bin/env python

import json
import time
import os
import base64
import urllib
import traceback
import logging

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
            # it expires.
            expiration = int(response_data['expires_in']) - 60
            memcache.set('oauth_bearer_token', oauth_token, time=expiration)

    if oauth_token is None:
        return {}

    return {'Authorization': 'Bearer ' + oauth_token}

class ClassEntry(ndb.Model):
    classId = ndb.IntegerProperty()
    name = ndb.StringProperty()

    @classmethod
    def get_mapping(cls):
        results = cls.query().fetch()
        if results:
            return dict((x.classId, x.name) for x in results)
        return {}

class Realm(ndb.Model):
    realm = ndb.StringProperty(indexed=True, required=True)
    slug = ndb.StringProperty(indexed=True, required=True)

    @classmethod
    def query_realm(cls, toon_realm):
        result = cls.query(cls.slug == toon_realm, namespace='Realms').fetch(1)[0]
        if result:
            return result.realm
        return ''

class Importer(object):

    WEAPON_ENCHANTS = [
        6227, # Ascended Vigor
        6226, # Eternal Grace
        6223, # Lightless Force
        6228, # Sinful Revelation
        6229, # Celestial Guidance

        # Hunter scopes
        6196, # Optical Target Embiggener

        # Death Knight runeforges
        3368, # Fallen Crusader
        3380, # Razorice
        6241, # Sanguination
        6243, # Hysteria
    ]

    RING_ENCHANTS = [
        6164, # Tenet of Crit
        6166, # Tenet of Haste
        6168, # Tenet of Mastery
        6170, # Tenet of Versatility
    ]

    CHEST_ENCHANTS = [
        6217, # Eternal Bounds
        6214, # Eternal Skirmish
        6230, # Eternal Stats
        6213, # Eternal Bulwark
        6265, # Eternal Insight
    ]

    CLOAK_ENCHANTS = [
        6208, # Soul Vitality
        6203, # Fortified Avoidance
        6204, # Fortified Leech
        6202, # Fortified Speed
    ]

    ENCHANTS = {
        'CHEST': CHEST_ENCHANTS,
        'BACK': CLOAK_ENCHANTS,
        'FINGER_1': RING_ENCHANTS,
        'FINGER_2': RING_ENCHANTS,
        'MAIN_HAND': WEAPON_ENCHANTS,
        'OFF_HAND': WEAPON_ENCHANTS
    }

    def load(self, realm, frealm, toonlist, data, groupstats):

        classes = ClassEntry.get_mapping()
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
                toonfrealm = Realm.query_realm(toonrealm)

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

            url = 'https://us.api.blizzard.com/profile/wow/character/%s/%s?namespace=profile-us&locale=en_US' % (toonrealm, urllib.quote(toonname.encode('utf-8').lower()))

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
        logging.info("Time spent retrieving data: %f seconds" % (end-start))

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, rpc, name, toondata, groupstats, classes):

        try:
            response = rpc.get_result()
        except Exception as e:
            handle_request_exception(e, 'profile', toondata)
            return

        toondata['name'] = name
        toondata['load_status'] = 'ok'

        # change the json from the response into a dict of data.
        try:
            jsondata = json.loads(response.content)
        except Exception as e:
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Failed to parse data from Blizzard. Refresh page to try again.'
            logging.exception('Failed to parse response as json: %s' % response.content)
            return

        # Catch HTTP errors from Blizzard. 404s really wreck everything.
        if not self.check_response_status(response, jsondata, 'profile', toondata):
            return;

        # store off some of the fields that we care about directly
        toondata['guild'] = jsondata.get('guild', {})
        toondata['realm'] = jsondata['realm']
        toondata['character_class'] = jsondata['character_class']
        toondata['name'] = jsondata['name']
        toondata['average_item_level'] = jsondata['average_item_level']
        toondata['equipped_item_level'] = jsondata['equipped_item_level']
        toondata['covenant'] = jsondata.get('covenant_progress',{}).get('chosen_covenant',{}).get('name','None')

        logging.info("got good results for %s" % name.encode('ascii', 'ignore'))

        # For each toon, update the statistics for the group as a whole
        if toondata['status'] == 'main':
            groupstats['ilvlmains'] += 1
            groupstats['totalilvl'] += jsondata['average_item_level']
            groupstats['totalilvleq'] += jsondata['equipped_item_level']

            toonclass = jsondata['character_class']['name']
            if toonclass in ['Paladin', 'Warrior', 'Death Knight']:
                groupstats['plate'] += 1
            elif toonclass in ['Mage', 'Priest', 'Warlock']:
                groupstats['cloth'] += 1
            elif toonclass in ['Druid', 'Monk', 'Rogue', 'Demon Hunter']:
                groupstats['leather'] += 1
            elif toonclass in ['Hunter', 'Shaman']:
                groupstats['mail'] += 1

            if toondata['role'] == 'dps':
                groupstats['melee'] += 1
            elif toondata['role'] == 'ranged':
                groupstats['ranged'] += 1
            elif toondata['role'] == 'tank':
                groupstats['tanks'] += 1
            elif toondata['role'] == 'healer':
                groupstats['healers'] += 1

        # We're also going to need the equipment for this character so make a second request
        oauth_headers = get_oauth_headers()
        try:
            equip_res = urlfetch.fetch("%s&locale=en_US" % jsondata['equipment']['href'], headers=oauth_headers)
        except Exception as e:
            handle_request_exception(e, 'equipment', toondata)
            return

        # change the json from the response into a dict of data.
        jsondata = json.loads(equip_res.content)

        # Catch HTTP errors from Blizzard. 404s really wreck everything.
        if not self.check_response_status(equip_res, jsondata, 'equipment', toondata):
            return;

        toondata['equipped_items'] = jsondata['equipped_items']

        # Group all gems together into a comma-separated list for tooltipParams
        for item in toondata['equipped_items']:
            if not isinstance(item, dict):
                continue

            item['tooltips'] = {}
            if 'sockets' in item:
                gems = []
                for socket in item['sockets']:
                    gems.append(socket.get('item', {}).get('id', 0))

                if gems:
                    item['tooltips']['gems'] = ':'.join(str(x) for x in gems)

            # Default enchant checking to -1 for all items
            item['enchant'] = -1

            slot = item['slot']['type']
            if slot in Importer.ENCHANTS:
                if slot != 'OFF_HAND' or 'weapon' in item:
                    item['enchant'] = 0
                    for enchant in item.get('enchantments', []):

                        # Skip non-permanent enchants
                        if enchant.get('enchantment_slot', {}).get('id', -1) != 0:
                            continue

                        enchant_id = enchant.get('enchantment_id', 0)
                        item['tooltips']['enchant'] = enchant_id
                        if enchant_id in Importer.ENCHANTS[slot] and item['enchant'] < 2:
                            item['enchant'] = 2
                        elif enchant != 0 and item['enchant'] < 1:
                            item['enchant'] = 1

    def create_callback(self, rpc, name, toondata, groupstats, classes):
        return lambda: self.handle_result(rpc, name, toondata, groupstats, classes)

    # Handles exceptions from requests to the API in a common fashion
    def handle_request_exception(self, exception, where, toondata):
        toondata['load_status'] = 'nok'

        if isinstance(urlfetch_errors.DeadlineExceededError, exception):
            logging.error('urlfetch threw DeadlineExceededError on toon %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = 'Timeout retrieving %s data from Battle.net for %s.  Refresh page to try again.' % (where, name)
        elif isinstance(urlfetch_errors.DownloadError, exception):
            logging.error('urlfetch threw DownloadError on toon %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = 'Network error retrieving %s data from Battle.net for toon %s.  Refresh page to try again.' % (where, name)
        else:
            logging.error('urlfetch threw unknown exception on toon %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = 'Unknown error retrieving %s data from Battle.net for toon %s.  Refresh page to try again.' % (where, name)

    # Checks response codes and error messages from the API in a common fashion.
    def check_response_status(self, response, jsondata, where, toondata):
        if response.status_code != 200 or ( 'code' in jsondata and 'detail' in jsondata ):
            code = jsondata.get('code', response.status_code)
            logging.error('urlfetch returned a %d status code on toon %s' % (code, toondata['name'].encode('ascii', 'ignore')))
            toondata['load_status'] = 'nok'
            toondata['reason'] = 'Got a %d requesting %s from Battle.net for toon %s.  Refresh page to try again.' % (code, where, toondata['name'])

            if 'detail' in jsondata:
                toondata['reason'] += ' (reason: %s)' % jsondata['detail']

            return False

        return True


class Setup(object):
    # Loads the list of realms into the datastore from the blizzard API so that
    # the realm list on the front page gets populated.  Also loads the list of
    # classes into a table on the DB so that we don't have to request it
    def initdb(self, app):
        try:
            oauth_headers = get_oauth_headers()
            realmcount = self.init_realms(oauth_headers)
            classcount = self.init_classes(oauth_headers)
            return [realmcount, classcount]
        except Exception as e:
            logging.exception('')
            return [0, 0]

    def init_realms(self, oauth_headers):
        # Delete all of the entities out of the realm datastore so fresh
        # entities can be loaded.
        query = Realm.query()
        for row in query.fetch():
            row.key.delete()

        # retrieve a list of realms from the blizzard API
        url = 'https://us.api.blizzard.com/data/wow/realm/index?namespace=dynamic-us&locale=en_US&region=us'
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
        url = 'https://us.api.blizzard.com/data/wow/playable-class/index?namespace=static-us&locale=en_US&region=us'
        response = urlfetch.fetch(url, headers=oauth_headers)
        if response.status_code == 200:
            jsondata = json.loads(response.content)
        else:
            jsondata = {'classes': []}

        for cls in jsondata['classes']:
            class_entry = ClassEntry(classId=cls['id'], name=cls['name'])
            class_entry.put()

        return len(jsondata['classes'])
