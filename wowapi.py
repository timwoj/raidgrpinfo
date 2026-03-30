# -*- coding: utf-8 -*-
#!/usr/bin/env python

import json
import time
import os
import base64
import urllib
import logging
import requests

from concurrent.futures import as_completed
from requests_futures.sessions import FuturesSession
from google.appengine.ext import ndb
from google.appengine.api import memcache

def get_oauth_headers():
    oauth_token = memcache.get('oauth_bearer_token')
    if oauth_token is None:
        path = os.path.join(os.path.split(__file__)[0], 'api-auth.json')
        authdata = json.load(open(path))

        credentials = "{}:{}".format(authdata['blizzard_client_id'], authdata['blizzard_client_secret'])
        encoded_credentials = base64.b64encode(credentials.encode('ascii')).decode('ascii')
        headers = {'Authorization': f'Basic {encoded_credentials}'}

        r = requests.post('https://us.battle.net/oauth/token',
                          data={'grant_type': 'client_credentials'},
                          headers=headers)

        if r.status_code == 200:
            response_data = r.json()
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

    # Each quality rank has its own list to allow for adjusting whether
    # low-rank enchants count as lesser enchants or not. These spell numbers
    # don't come from wowhead, but from the game data itself. I don't see
    # how to generate them from the HTTP API, but they can be extracted from
    # the game data itself.
    #
    # To do so, grab the simc source from github and run these commands:
    # cd casc_extract
    # python3 -m venv venv
    # source venv/bin/activate
    # pip3 install -r requirements.txt
    # python3 casc_extract.py -m batch --cdn -o wow
    #
    # cd ../dbc_extract3
    # python3 -m venv venv
    # source venv/bin/activate
    # pip3 install -r requirements.txt
    # ./generate.sh 11.1.0.59538 ../casc_extract/wow (where the version number
    #      comes from the latest version extracted by casc_extract)
    #
    # cat ../engine/dbc/generated/permanent_enchant.inc

    WEAPON_ENCHANTS_R1 = [
        8038, # Acuity of The Ren'dorei (Rank 1)
        8040, # Arcane Mastery (Rank 1)
        7982, # Berserker's Rage (Rank 1)
        8036, # Flames of the Sin'dorei (Rank 1)
        7980, # Jan'alai's Precision (Rank 1)
        7978, # Strength of Halazzi (Rank 1)
        8008, # Worldsoul Aegis (Rank 1)
        8006, # Worldsoul Cradle (Rank 1)
        8010, # Worldsoul Tenacity (Rank 1)
    ]

    WEAPON_ENCHANTS_R2 = [
        8039, # Acuity of The Ren'dorei (Rank 2)
        8041, # Arcane Mastery (Rank 2)
        7983, # Berserker's Rage (Rank 2)
        8037, # Flames of the Sin'dorei (Rank 2)
        7981, # Jan'alai's Precision (Rank 2)
        7979, # Strength of Halazzi (Rank 2)
        8009, # Worldsoul Aegis (Rank 2)
        8007, # Worldsoul Cradle (Rank 2)
        8011, # Worldsoul Tenacity (Rank 2)
    ]

    DEATH_KNIGHT_RUNEFORGES = [
        3368, # Fallen Crusader
        3380, # Razorice
        6241, # Sanguination
        6243, # Hysteria
    ]

    HEAD_ENCHANTS_R1 = [
        7988, # Blessing of Speed (Rank 1)
        7958, # Hex of Leeching (Rank 1)
        8014, # Rune of Avoidance (Rank 1)
        7990, # Empowered Blessing of Speed (Rank 1)
        7960, # Empowered Hex of Leeching (Rank 1)
        8016, # Empowered Rune of Avoidance (Rank 1)
    ]

    HEAD_ENCHANTS_R2 = [
        7989, # Blessing of Speed (Rank 2)
        7959, # Hex of Leeching (Rank 2)
        8015, # Rune of Avoidance (Rank 2)
        7991, # Empowered Blessing of Speed (Rank 2)
        7961, # Empowered Hex of Leeching (Rank 2)
        8017, # Empowered Rune of Avoidance (Rank 2)
    ]

    RING_ENCHANTS_R1 = [
        7964, # Amani Mastery (Rank 1)
        7966, # Eyes of the Eagle (Rank 1)
        7996, # Nature's Fury (Rank 1)
        7994, # Nature's Wrath (Rank 1)
        8024, # Silvermoon's Alacrity (Rank 1)
        8026, # Silvermoon's Tenacity (Rank 1)
        8020, # Thalassian Haste (Rank 1)
        8022, # Thalassian Versatility (Rank 1)
        7968, # Zul'jin's Mastery (Rank 1)
    ]

    RING_ENCHANTS_R2 = [
        7965, # Amani Mastery (Rank 2)
        7967, # Eyes of the Eagle (Rank 2)
        7997, # Nature's Fury (Rank 2)
        7995, # Nature's Wrath (Rank 2)
        8025, # Silvermoon's Alacrity (Rank 2)
        8027, # Silvermoon's Tenacity (Rank 2)
        8021, # Thalassian Haste (Rank 2)
        8023, # Thalassian Versatility (Rank 2)
        7969, # Zul'jin's Mastery (Rank 2)
    ]

    SHOULDER_ENCHANTS_R1 = [
        7976, # Akil'zon's Swiftness (Rank 1)
        8000, # Amirdrassil's Grace (Rank 1)
        7970, # Flight of the Eagle (Rank 1)
        7998, # Nature's Grace (Rank 1)
        8030, # Silvermoon's Mending (Rank 1)
        8028, # Thalassian Recovery (Rank 1)
    ]

    SHOULDER_ENCHANTS_R2 = [
        7977, # Akil'zon's Swiftness (Rank 2)
        8001, # Amirdrassil's Grace (Rank 2)
        7971, # Flight of the Eagle (Rank 2)
        7999, # Nature's Grace (Rank 2)
        8031, # Silvermoon's Mending (Rank 2)
        8029, # Thalassian Recovery (Rank 2)
    ]

    LEG_ENCHANTS_R1 = [
        8162, # Blood Knight's Armor Kit (Rank 1)
        8158, # Forest Hunter's Armor Kit (Rank 1)
        8160, # Thalassian Scout Armor Kit (Rank 1)
        7936, # Arcanoweave Spellthread (Rank 1)
        7934, # Sunfire Silk Spellthread (Rank 1)
        7938, # Bright Linen Spellthread (Rank 1)
    ]

    LEG_ENCHANTS_R2 = [
        8163, # Blood Knight's Armor Kit (Rank 1)
        8159, # Forest Hunter's Armor Kit (Rank 1)
        8161, # Thalassian Scout Armor Kit (Rank 1)
        7937, # Arcanoweave Spellthread (Rank 1)
        7935, # Sunfire Silk Spellthread (Rank 1)
        7939, # Bright Linen Spellthread (Rank 1)
    ]

    CHEST_ENCHANTS_R1 = [
        7956, # Mark of Nalorakk (Rank 1)
        8012, # Mark of the Magister (Rank 1)
        7984, # Mark of the Rootwarden (Rank 1)
        7986, # Mark of the Worldsoul (Rank 1)
    ]

    CHEST_ENCHANTS_R2 = [
        7957, # Mark of Nalorakk (Rank 2)
        8013, # Mark of the Magister (Rank 2)
        7985, # Mark of the Rootwarden (Rank 2)
        7987, # Mark of the Worldsoul (Rank 2)
    ]

    FEET_ENCHANTS_R1 = [
        8018, # Farstrider's Hunt (Rank 1)
        7962, # Lynx's Dexterity (Rank 1)
        7992, # Shaladrassil's Roots (Rank 1)
    ]

    FEET_ENCHANTS_R2 = [
        8019, # Farstrider's Hunt (Rank 2)
        7963, # Lynx's Dexterity (Rank 2)
        7993, # Shaladrassil's Roots (Rank 2)
    ]

    # Join the lists that will be considered "Lesser" enchants
    ENCHANTS = {
        'CHEST': CHEST_ENCHANTS_R1,
        'SHOULDER': SHOULDER_ENCHANTS_R1,
        'HEAD': HEAD_ENCHANTS_R1,
        'LEGS': LEG_ENCHANTS_R1,
        'FEET': FEET_ENCHANTS_R1,
        'FINGER_1': RING_ENCHANTS_R1,
        'FINGER_2': RING_ENCHANTS_R1,
        'MAIN_HAND': WEAPON_ENCHANTS_R1,
        'OFF_HAND': WEAPON_ENCHANTS_R1,
    }

    BETTER_ENCHANTS = {
        'CHEST': CHEST_ENCHANTS_R2,
        'SHOULDER': SHOULDER_ENCHANTS_R2,
        'HEAD': HEAD_ENCHANTS_R2,
        'LEGS': LEG_ENCHANTS_R2,
        'FEET': FEET_ENCHANTS_R2,
        'FINGER_1': RING_ENCHANTS_R2,
        'FINGER_2': RING_ENCHANTS_R2,
        'MAIN_HAND': WEAPON_ENCHANTS_R2 + DEATH_KNIGHT_RUNEFORGES,
        'OFF_HAND': WEAPON_ENCHANTS_R2
    }

    CLASS_ARMOR = {
        'Death Knight': 'plate',
        'Demon Hunter': 'leather',
        'Evoker': 'mail',
        'Druid': 'leather',
        'Hunter': 'mail',
        'Mage': 'cloth',
        'Monk': 'leather',
        'Paladin': 'plate',
        'Priest': 'cloth',
        'Rogue': 'leather',
        'Shaman': 'mail',
        'Warlock': 'cloth',
        'Warrior': 'plate'
    }

    def load(self, realm, frealm, toonlist, data, groupstats):

        classes = ClassEntry.get_mapping()
        oauth_headers = get_oauth_headers()

        session = FuturesSession(max_workers=10)
        futures = []

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

            quoted_name = urllib.parse.quote(toonname.encode('utf-8').lower())
            url = f'https://us.api.blizzard.com/profile/wow/character/{toonrealm}/{quoted_name}?namespace=profile-us&locale=en_US'

            # create the rpc object for the fetch method.  the deadline
            # defaults to 5 seconds, but that seems to be too short for the
            # Blizzard API site sometimes.  setting it to 10 helps a little
            # but it makes page loads a little slower.
            future = session.get(url, headers=oauth_headers)
            future.toonname = toonname
            future.toondata = newdata
            futures.append(future)

            # This really shouldn't happen, but pause a half-second every
            # hundred toons so that we don't blow through the API quota.
            toon_count = toon_count + 1
            if toon_count > 100:
                time.sleep(0.5)
                toon_count = 0

        # Now that all of the RPC calls have been created, loop through the data
        # dictionary one more time and wait for each fetch to be completed. Once
        # all of the waits finish, then we have all of the data from the
        # Blizzard API and can loop through all of it and build the page.
        start = time.time()
        for future in as_completed(futures):
            resp = future.result()
            self.handle_result(resp, future.toonname, future.toondata,
                               groupstats, classes)
        end = time.time()
        logging.info(f"Time spent retrieving data: {end-start} seconds")

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, response, name, toondata, groupstats, classes):

        toondata['name'] = name
        toondata['load_status'] = 'ok'

        # change the json from the response into a dict of data.
        try:
            jsondata = response.json()
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
            logging.info("%s" % toonclass)
            groupstats[Importer.CLASS_ARMOR.get(toonclass, '')] += 1

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
            equip_res = requests.get(f"{jsondata['equipment']['href']}&locale=en_US",
                                     headers=oauth_headers)
        except Exception as e:
            self.handle_request_exception(e, 'equipment', toondata)
            return

        # change the json from the response into a dict of data.
        jsondata = equip_res.json()

        # Catch HTTP errors from Blizzard. 404s really wreck everything.
        if not self.check_response_status(equip_res, jsondata, 'equipment', toondata):
            return;

        toondata['equipped_items'] = jsondata.get('equipped_items', [])

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
                        if enchant_id in Importer.BETTER_ENCHANTS[slot] and item['enchant'] < 2:
                            item['enchant'] = 2
                        elif enchant_id in Importer.ENCHANTS[slot] and item['enchant'] < 1:
                            item['enchant'] = 1

    # Handles exceptions from requests to the API in a common fashion
    def handle_request_exception(self, exception, where, toondata):
        toondata['load_status'] = 'nok'

        if isinstance(exception, requests.Timeout):
            logging.error('request timed out on toon %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = f'Timeout retrieving {where} data from Battle.net for {name}. Refresh page to try again.'
        elif isinstance(exception, requests.ConnectionError):
            logging.error('request failed to connect for %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = f'Failed to connect to Battle.net when retrieving {where} for toon {name}'
        else:
            logging.error('request threw unknown exception on toon %s' % name.encode('ascii', 'ignore'))
            toondata['reason'] = f'Unknown error retrieving {where} data from Battle.net for toon {name}.  Refresh page to try again.'

    # Checks response codes and error messages from the API in a common fashion.
    def check_response_status(self, response, jsondata, where, toondata):
        if response.status_code != 200 or ( 'code' in jsondata and 'detail' in jsondata ):
            code = jsondata.get('code', response.status_code)
            logging.error('request returned a %d status code on toon %s' % (code, toondata['name'].encode('ascii', 'ignore')))
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
        response = requests.get(url, headers=oauth_headers)
        if response.status_code == 200:
            jsondata = response.json()
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
        response = requests.get(url, headers=oauth_headers)
        if response.status_code == 200:
            jsondata = response.json()
        else:
            jsondata = {'classes': []}

        for cls in jsondata['classes']:
            class_entry = ClassEntry(classId=cls['id'], name=cls['name'])
            class_entry.put()

        return len(jsondata['classes'])
