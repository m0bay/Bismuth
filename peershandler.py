"""
Peers handler module for Bismuth nodes
@EggPoolNet
"""

import json, time, re, os
import threading

import socks

__version__ = "0.0.5"


# TODO : some config options are _conf and others without => clean up later on

def most_common(lst):
    """Used by consensus"""
    return max(set(lst), key=lst.count)


class Peers:
    """The peers manager. A thread safe peers manager"""

    __slots__ = ('app_log','config','logstats','peersync_lock','startup_time','reset_time','warning_list','stats','connection_pool',
                'peer_ip_list','consensus_blockheight_list','consensus_percentage','consensus','tried','peer_dict','connection_pool','peerlist','banlist','whitelist','ban_threshold')

    def __init__(self, app_log, config=None, logstats=True):
        self.app_log = app_log
        self.config = config
        self.logstats = logstats

        self.peersync_lock = threading.Lock()
        self.startup_time = time.time()
        self.reset_time = self.startup_time
        self.warning_list = []
        self.stats = []
        self.connection_pool = []
        self.peer_ip_list = []
        self.consensus_blockheight_list = []
        self.consensus_percentage = 0
        self.consensus = None
        self.tried = []
        self.peer_dict = {}
        self.connection_pool = []
        # We store them apart from the initial config, could diverge somehow later on.
        self.banlist = config.banlist
        self.whitelist = config.whitelist
        self.ban_threshold = config.ban_threshold

        # From manager(), init
        self.peer_dict.update(self.peers_get("peers.txt"))
        self.peers_test("peers.txt")
        self.peers_test("suggested_peers.txt")

        self.peerlist = "peers.txt"
        if self.is_testnet: #overwrite for testnet
            self.peerlist = "peers_test.txt"

    @property
    def is_testnet(self):
        """Helper to check if testnet or not. Only one place to change variable names and test"""
        return "testnet" in self.config.version_conf

    def status_dict(self):
        """Returns a status as a dict"""
        status={"version":self.config.VERSION,"stats":self.stats}
        return status

    def peers_save(self, peerlist, peer_ip):
        """Validates then adds a peer to the peer list on disk"""
        # called by Sync, should not be an issue, but check if needs to be thread safe or not.
        peer_file = open(peerlist, 'r')
        peer_tuples = []
        for line in peer_file:
            extension = re.findall("'([\d\.]+)', '([\d]+)'", line)
            peer_tuples.extend(extension)
        peer_file.close()
        peer_tuple = ("('" + peer_ip + "', '" + str(self.config.port) + "')")

        try:
            if peer_tuple not in str(peer_tuples):
                self.app_log.warning("Testing connectivity to: {}".format(peer_ip))
                peer_test = socks.socksocket()
                if self.config.tor_conf == 1:
                    peer_test.setproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
                peer_test.connect((str(peer_ip), int(self.config.port)))  # double parentheses mean tuple
                self.app_log.info("Inbound: Distant peer connectible")

                # properly end the connection
                peer_test.close()
                # properly end the connection

                peer_list_file = open(peerlist, 'a')
                peer_list_file.write((peer_tuple) + "\n")
                self.app_log.info("Inbound: Distant peer saved to peer list")
                peer_list_file.close()
            else:
                self.app_log.info("Distant peer already in peer list")
        except:
            self.app_log.info("Inbound: Distant peer not connectible")
            pass

    def append_client(self, client):
        # TODO: thread safe?
        self.connection_pool.append(client)

    def remove_client(self, client):
        # TODO: thread safe?
        self.connection_pool.remove(client)

    def unban(self, peer_ip):
        """Removes the peer_ip from the warning list"""
        # TODO: Not thread safe atm. Should use a thread aware list or some lock
        if peer_ip in self.warning_list:
            self.warning_list.remove(peer_ip)
            self.app_log.warning("Removed a warning for {}".format(peer_ip))

    def warning(self, sdef, ip, reason, count):
        """Adds a weighted warning to a peer."""
        # TODO: Not thread safe atm. Should use a thread aware list or some lock
        if ip not in self.whitelist:
            # TODO: use a dict instead of several occurences in a list
            for x in range(count):
                self.warning_list.append(ip)
            self.app_log.warning("Added {} warning(s) to {}: {} ({} / {})".format(count, ip, reason, self.warning_list.count(ip), self.ban_threshold))

            if self.warning_list.count(ip) >= self.ban_threshold:
                self.banlist.append(ip)
                sdef.close()
                self.app_log.warning("{} is banned: {}".format(ip, reason))
                return True
            else:
                return False

    def peers_get(self, peerlist):
        """Returns a peerlist from disk as a dict {ip:port}"""
        peer_dict = {}
        if not os.path.exists(peerlist):
            open(peerlist, "a").close()

        with open(peerlist, "r") as f:
            for line in f:
                try:
                    line = re.sub("[\)\(\:\\n\'\s]", "", line)
                    peer_dict[line.split(",")[0]] = line.split(",")[1]
                except Exception as e:
                    self.app_log.warning("Skipping peerlist entry because of wrong format: {}".format(line))
        return peer_dict


    def peer_list(self, peerlist):
        """Returns a peerlist as is, simple text format"""
        # TODO: caching and format to handle here
        with open(peerlist, "r") as peer_list:
            peers = peer_list.read()
        return peers

    @property
    def consensus_most_common(self):
        """Consensus vote"""
        try:
            return most_common(self.consensus_blockheight_list)
        except:
            # no consensus yet
            return 0

    @property
    def consensus_max(self):
        try:
            return max(self.consensus_blockheight_list)
        except:
            # no consensus yet
            return 0

    @property
    def consensus_size(self):
        """Number of nodes in consensus"""
        return len(self.consensus_blockheight_list)

    def is_allowed(self, peer_ip, command=''):
        """Tells if the given peer is allowed for that command"""
        # TODO: more granularity here later
        # Always allow whitelisted ip to post as block
        if 'block' == command and self.is_whitelisted(peer_ip):
            return True
        return peer_ip in self.config.allowed_conf or "any" in self.config.allowed_conf

    def is_whitelisted(self, peer_ip, command=''):
        # TODO: could be handled later on via "allowed" and rights.
        return peer_ip in self.whitelist or "127.0.0.1" ==peer_ip

    def is_banned(self, peer_ip):
        return peer_ip in self.banlist

    def peers_test(self, peerlist):
        """Tests all peers from a list."""
        # TODO: lengthy, no need to test everyone at once?
        if self.peersync_lock.locked() == False and self.config.accept_peers == "yes":
            self.peersync_lock.acquire()

            drop_peer_dict = []
            peer_dict = self.peers_get(peerlist)

            for key, value in peer_dict.items():
                HOST = key
                PORT = int(value)

                try:
                    s = socks.socksocket()
                    s.settimeout(0.6)
                    if self.config.tor_conf == 1:
                        s.settimeout(5)
                        s.setproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
                    s.connect((HOST, PORT))
                    s.close()
                    self.app_log.info("Connection to {} {} successful, keeping the peer".format(HOST ,PORT))
                except:
                    if self.config.purge_conf == 1 and not self.is_testnet:
                        # remove from peerlist if not connectible
                        drop_peer_dict.append(key)
                        self.app_log.info("Removed formerly active peer {} {}".format(HOST, PORT))
                    pass

            output = open(peerlist, 'w')
            for key, value in peer_dict.items():
                if key not in drop_peer_dict:
                    output.write("('" + key + "', '" + value + "')\n")
            output.close()
            self.peersync_lock.release()


    def peersync(self, subdata):
        """Got a peers list from a peer, process. From worker()."""
        if self.peersync_lock.locked() == False and self.config.accept_peers == "yes":
            self.peersync_lock.acquire()

            # get remote peers into tuples (actually list)
            server_peer_tuples = re.findall("'([\d\.]+)', '([\d]+)'", subdata)
            self.app_log.info("Received following {} peers: {}".format(len((server_peer_tuples)), server_peer_tuples))
            # get remote peers into tuples (actually list)

            # get local peers into tuples
            peer_file = open(self.peerlist, 'r')
            peer_tuples = []
            for line in peer_file:
                extension = re.findall("'([\d\.]+)', '([\d]+)'", line)
                peer_tuples.extend(extension)
            peer_file.close()
            # get local peers into tuples

            for x in set(server_peer_tuples):  # set removes duplicates
                if x not in peer_tuples:
                    self.app_log.info("Outbound: {} is a new peer, saving if connectible".format(x))
                    try:
                        s_purge = socks.socksocket()
                        s_purge.settimeout(0.2)
                        if self.config.tor_conf == 1:
                            s_purge.settimeout(5)
                            s_purge.setproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)

                        s_purge.connect((x[0], int(x[1])))  # save a new peer file with only active nodes
                        s_purge.close()

                        peer_formatted = "('" + x[0] + "', '" + x[1] + "')"
                        if peer_formatted not in open('suggested_peers.txt').read():
                            peer_list_file = open("suggested_peers.txt", 'a')
                            peer_list_file.write(peer_formatted+"\n")
                            peer_list_file.close()
                    except:
                        pass
                        self.app_log.info("Not connectible")

                else:
                    self.app_log.info("Outbound: {} is not a new peer".format(x))
            self.peersync_lock.release()
        else:
            self.app_log.info("Outbound: Peer sync occupied")


    def consensus_add(self, peer_ip, consensus_blockheight, sdef, last_block):
        # obviously too old blocks, we have half a day worth of validated blocks after them
        # no ban, they can (should) be syncing but they can't possibly be in consensus list.
        too_old = last_block - 720
        try:
            if peer_ip not in self.peer_ip_list:
                if consensus_blockheight < too_old:
                    # should change to .info later on
                    self.app_log.warning("{} got too old a block ({}) for consensus".format(peer_ip,consensus_blockheight));
                    return
                self.app_log.info("Adding {} to consensus peer list".format(peer_ip))
                self.peer_ip_list.append(peer_ip)
                self.app_log.info("Assigning {} to peer block height list".format(consensus_blockheight))
                self.consensus_blockheight_list.append(str(int(consensus_blockheight)))

            if peer_ip in self.peer_ip_list:
                consensus_index = self.peer_ip_list.index(peer_ip)  # get where in this list it is

                if self.consensus_blockheight_list[consensus_index] == (consensus_blockheight):
                    self.app_log.info("Opinion of {} hasn't changed".format(peer_ip))

                else:
                    del self.peer_ip_list[consensus_index]  # remove ip
                    del self.consensus_blockheight_list[consensus_index]  # remove ip's opinion
                    if consensus_blockheight < too_old:
                        # should change to .info later on
                        self.app_log.warning("{} got too old a block ({})for consensus".format(peer_ip,consensus_blockheight));
                        return
                    self.app_log.info("Updating {} in consensus".format(peer_ip))
                    self.peer_ip_list.append(peer_ip)
                    self.consensus_blockheight_list.append(int(consensus_blockheight))

            self.consensus = most_common(self.consensus_blockheight_list)

            self.consensus_percentage = (float(
                self.consensus_blockheight_list.count(self.consensus) / float(len(self.consensus_blockheight_list)))) * 100

            if int(consensus_blockheight) > int(self.consensus) + 30 and self.consensus_percentage > 50 and len(self.consensus_blockheight_list) > 10:
                if self.warning(sdef, peer_ip, "Consensus deviation too high", 10) == True:
                    raise ValueError("{} banned".format(peer_ip))

            return
        except Exception as e:
            self.app_log.info(e)
            raise


    def consensus_remove(self, peer_ip):
        try:
            self.app_log.info("Consensus opinion list: {}".format(self.consensus_blockheight_list))
            self.app_log.info("Will remove {} from consensus pool {}".format(peer_ip, self.peer_ip_list))
            consensus_index = self.peer_ip_list.index(peer_ip)
            self.peer_ip_list.remove(peer_ip)
            del self.consensus_blockheight_list[consensus_index]  # remove ip's opinion
        except:
            self.app_log.info("IP of {} not present in the consensus pool".format(peer_ip))
            pass

    def manager_loop(self, target=None):
        """Manager loop called every 30 sec. Handles maintenance"""
        variability = [] #prevent ip range attack (excluding inc conns)
        del variability [:]
        variable = []
        del variable [:]

        for key, value in self.peer_dict.items():
            variability.append(key.split(".")[:-1])

        for x in variability:
            if variability.count(x) < 3:
                variable.append(".".join(x))

        for key, value in self.peer_dict.items():
            HOST = key
            PORT = int(value)

            for x in variable:
                if x in HOST:
                    if self.is_testnet:
                        PORT = 2829

                    if threading.active_count()/3 < self.config.thread_limit_conf and str(HOST + ":" + str(PORT)) not in self.tried and str(HOST + ":" + str(PORT)) not in self.connection_pool and str(HOST) not in self.banlist:
                        self.app_log.info("Will attempt to connect to {}:{}".format(HOST, PORT))
                        self.tried.append(HOST + ":" + str(PORT))
                        t = threading.Thread(target=target, args=(HOST, PORT))  # threaded connectivity to nodes here
                        self.app_log.info("---Starting a client thread " + str(threading.currentThread()) + "---")
                        t.daemon = True
                        t.start()

        # TODO: 15 s after start is too short for all peers to have been tested, rework needed.
        if int(time.time() - self.startup_time) > 15: #refreshes peers from drive
            self.peer_dict.update(self.peers_get(self.peerlist))

        if len(self.consensus_blockheight_list) < 3 and int(time.time() - self.startup_time) > 15: #join in random peers after x seconds
            self.app_log.warning("Not enough peers in consensus, joining in peers suggested by other nodes")
            self.peer_dict.update(self.peers_get("suggested_peers.txt"))

        if len(self.connection_pool) < self.config.nodes_ban_reset and int(time.time() - self.startup_time) > 15: #do not reset before 30 secs have passed
            self.app_log.warning("Only {} connections active, resetting banlist".format(len(self.connection_pool)))
            del self.banlist[:]
            self.banlist.extend(self.config.banlist) # reset to config version
            del self.warning_list[:]

        if len(self.connection_pool) < 10:
            self.app_log.warning("Only {} connections active, resetting the connection history".format(len(self.connection_pool)))
            del self.tried[:]

        if self.config.nodes_ban_reset and len(self.connection_pool) <= len(self.banlist) and int(time.time() - self.reset_time) > 60*10: #do not reset too often. 10 minutes here
            self.app_log.warning("Less active connections ({}) than banlist ({}), resetting banlist and tried" .format(len(self.connection_pool), len(self.banlist)))
            del self.banlist[:]
            self.banlist.extend(self.config.banlist) # reset to config version
            del self.warning_list[:]
            del self.tried[:]
            self.reset_time = time.time()

    def status_log(self):
        """Prints the peers part of the node status"""
        self.app_log.warning("Total number of known peers: {}".format(len(self.peer_dict)))
        if self.banlist:
            self.app_log.warning("Status: Banlist: {}".format(self.banlist))
            self.app_log.warning("Status: Banlist Count : {}".format(len(self.banlist)))
        if self.whitelist:
            self.app_log.warning("Status: Whitelist: {}".format(self.whitelist))

        self.app_log.info("Status: Tried: {}".format(self.tried))
        self.app_log.info("Status: Tried Count: {}".format(len(self.tried)))
        self.app_log.info("Status: List of Outbound connections: {}".format(self.connection_pool))
        self.app_log.warning("Status: Number of Outbound connections: {}".format(len(self.connection_pool)))
        if self.consensus:  # once the consensus is filled
            self.app_log.warning("Status: Consensus: {} = {}%".format(self.consensus, self.consensus_percentage))
            self.app_log.warning("Status: Consensus IP list: {}".format(self.peer_ip_list))
            self.app_log.warning("Status: Consensus opinion list: {}".format(self.consensus_blockheight_list))
            self.app_log.warning("Status: Total number of nodes: {}".format(len(self.consensus_blockheight_list)))