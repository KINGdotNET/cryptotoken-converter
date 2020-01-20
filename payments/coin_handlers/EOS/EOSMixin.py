"""
**Copyright**::

    +===================================================+
    |                 © 2019 Privex Inc.                |
    |               https://www.privex.io               |
    +===================================================+
    |                                                   |
    |        CryptoToken Converter                      |
    |                                                   |
    |        Core Developer(s):                         |
    |                                                   |
    |          (+)  Chris (@someguy123) [Privex]        |
    |                                                   |
    +===================================================+

"""
import logging
from typing import Dict, Any, List, Optional

from payments.coin_handlers.base import SettingsMixin
from eospy.cleos import Cleos

from payments.coin_handlers.base.exceptions import TokenNotFound, MissingTokenMetadata
from payments.models import Coin
from steemengine.helpers import empty

log = logging.getLogger(__name__)


class EOSMixin(SettingsMixin):
    """
    EOSMixin - A child class of SettingsMixin that is used by both EOSLoader and EOSManager for shared functionality.

    Main features::

     - Access the EOS shared instance via :py:attr:`.eos`
     - Get the general ``EOS`` symbol coin settings via :py:attr:`.eos_settings`
     - Access individual token settings (e.g. contract) via ``self.settings[symbol]``
     - Helper method :py:meth:`.get_contract` - get contract via DB, or fall back to :py:attr:`.default_contracts`
     - Automatically sets setting defaults, such as the RPC node (using Greymass node over SSL)

    **Copyright**::

        +===================================================+
        |                 © 2019 Privex Inc.                |
        |               https://www.privex.io               |
        +===================================================+
        |                                                   |
        |        CryptoToken Converter                      |
        |                                                   |
        |        Core Developer(s):                         |
        |                                                   |
        |          (+)  Chris (@someguy123) [Privex]        |
        |                                                   |
        +===================================================+

    """

    chain = 'eos'
    """
    This controls the name of the chain and is used for logging, cache keys etc.
    It may be converted to upper case for logging, and lower case for cache keys.
    Forks of EOS may override this when sub-classing EOSMixin to adjust logging, cache keys etc.
    """
    chain_type = chain
    """
    Used for looking up 'coin_type=xxx'
    Forks of EOS should override this to match the coin_type they use for :py:attr:`.provides` generation
    """
    chain_coin = 'EOS'
    """
    Forks of EOS may override this when sub-classing EOSMixin to change the native coin symbol of the network
    """

    setting_defaults = dict(
        host='eos.greymass.com', username=None, password=None, endpoint='/', port=443, ssl=True, precision=4,
        telos=False, history_url='https://eos-history.privex.io', load_method='actions'
    )   # type: Dict[str, Any]
    """
    Default settings to use if any required values are empty, e.g. default to Greymass's RPC node
    
    ``load_method`` can be either ``pvx`` for Privex EOS History API, or ``actions`` to use v1/history from the RPC node.
    """
    
    provides = ['EOS']  # type: List[str]
    """
    This attribute is automatically generated by scanning for :class:`models.Coin` s with the type ``eos``. 
    This saves us from hard coding specific coin symbols. See __init__.py for populating code.
    """

    default_contracts = {
        'EOS': 'eosio.token',
    }   # type: Dict[str, str]
    """
    To make it easier to add common tokens on the EOS network, the loader/manager will fallback to this map between
    symbols and contracts.
     
    This means that you don't have to set the contract in the custom JSON for popular tokens in this list, such as
    the native EOS token (which uses the contract account eosio.token).
    """

    _eos = None   # type: Cleos
    """Shared instance of :py:class:`eospy.cleos.Cleos` used across both the loader/manager."""
    
    current_rpc: Optional[str]
    """Contains the current EOS API node as a string"""
    
    def __init__(self):
        self.current_rpc = None
    
    @property
    def all_coins(self) -> Dict[str, Coin]:
        """
        Ensures that the coin 'EOS' always has it's settings loaded by :py:class:`base.SettingsMixin` by overriding
        this method ``all_coins`` to inject the coin EOS if it's not our symbol.

        :return dict coins: A dict<str,Coin> of supported coins, mapped by symbol
        """
        c = {}
        if hasattr(self, 'coins'):
            c = dict(self.coins)
        elif hasattr(self, 'coin'):
            c = {self.coin.symbol_id: self.coin}
        else:
            raise Exception('Cannot load settings as neither self.coin nor self.coins exists...')

        coin = self.chain_coin
        if coin not in c:
            coin_type = self.chain_type
            try:
                c[coin] = Coin.objects.get(symbol=coin, coin_type=coin_type)
            except Coin.DoesNotExist:
                log.warning(f'EOSMixin cannot find a coin with the symbol "{coin}" and type "{coin_type}"...')
                log.warning(f'Checking for a coin with native symbol_id "{coin}" and type "{coin_type}"...')
                c[coin] = Coin.objects.get(symbol_id=coin, coin_type=coin_type)
            return c
        return c

    @property
    def settings(self) -> Dict[str, dict]:
        """
        Get all settings, mapped by coin symbol (each coin symbol dict contains custom json settings merged)

        :return dict settings: A dictionary mapping coin symbols to settings
        """
        if len(self._settings) > 0:
            return self._settings
        return self._prep_settings()

    @property
    def eos_settings(self) -> Dict[str, Any]:
        """
        Since EOS deals with tokens under one network, this is a helper property to quickly get the base EOS settings

        :return dict settings: A map of setting keys to their values
        """
        return super(EOSMixin, self).settings.get(self.chain_coin, self.setting_defaults)

    @property
    def eos(self) -> Cleos:
        """Returns an instance of Cleos and caches it in the attribute _eos after creation"""
        if not self._eos:
            log.debug(f'Creating Cleos instance using {self.chain.upper()} API node: {self.url}')
            self.current_rpc = self.url
            self._eos = Cleos(url=self.url)
        return self._eos
    
    def replace_eos(self, **conn) -> Cleos:
        """
        Destroy the EOS :class:`.Cleos` instance at :py:attr:`._eos` and re-create it with the modified
        connection settings ``conn``
        
        Also returns the EOS instance for convenience.
        
        Only need to specify settings you want to override.
        
        Example::
        
            >>> eos = self.replace_eos(host='example.com', port=80, ssl=False)
            >>> eos.get_account('someguy123')
        
        
        :param conn: Connection settings. Keys: endpoint, ssl, host, port, username, password
        :return Cleos eos: A :class:`.Cleos` instance with the modified connection settings.
        """
        del self._eos
        url = self._make_url(**conn)
        log.debug('Replacing Cleos instance with new %s API node: %s', self.chain.upper(), url)
        self.current_rpc = url
        self._eos = Cleos(url=url)
        
        return self._eos
    
    @property
    def url(self) -> str:
        """Creates a URL from the host settings on the EOS coin"""
        return self._make_url(**self.eos_settings)

    def _make_url(self, **conn) -> str:
        """
        Generate a Cleos connection URL.
        
        Only need to specify settings you want to override.
        
        Example::
        
            >>> self._make_url(host='example.org', endpoint='/eosrpc')
            'https://example.org:443/eosrpc'
        
        :param conn: Connection settings. Keys: endpoint, ssl, host, port, username, password
        :return str url: Generated URL
        """
        s = {**self.setting_defaults, **conn}
        
        url = s['endpoint']
        proto = 'https' if s['ssl'] else 'http'
        host = '{}:{}'.format(s['host'], s['port'])
    
        if s['username'] is not None:
            host = '{}:{}@{}:{}'.format(s['username'], s['password'], s['host'], s['port'])
    
        url = url[1:] if len(url) > 0 and url[0] == '/' else url  # Strip starting / of URL
        url = "{}://{}/{}".format(proto, host, url)
        # Cleos doesn't like ending slashes, so make sure to remove any ending slashes...
        url = url[:-1] if url[-1] == '/' else url
        return url

    def get_contract(self, symbol: str) -> str:
        """
        Attempt to find the contract account for a given token symbol, searches the database Coin objects first
        using :py:attr:`.settings` - if not found, falls back to :py:attr:`.default_contracts`

        Example usage::

            >>> contract_acc = self.get_contract('EOS')
            >>> print(contract_acc)
             eosio.token


        :param str symbol:              The token symbol to find the contract for, e.g. ``EOS``
        :raises TokenNotFound:          The given ``symbol`` does not exist in self.settings
        :raises MissingTokenMetadata:   Could not find contract in DB coin settings nor default_contracts
        :return str contract_acc:       The contract username as a string, e.g. ``eosio.token``
        """

        symbol = symbol.upper()
        log.debug(f'Attempting to find {self.chain.upper()} contract for "{symbol}" in DB Coin settings')

        try:
            contract = self.settings[symbol].get('contract')
            if not empty(contract):
                return contract
        except AttributeError:
            raise TokenNotFound(f'The coin "{symbol}" was not found in {__name__}.settings')

        log.debug(f'No contract found in DB settings for "{symbol}", checking if we have a default...')
        try:
            contract = self.default_contracts[symbol]

            if empty(contract):
                raise MissingTokenMetadata

            log.debug(f'Found contract for "{symbol}" in default_contracts, returning "{contract}"')
            return contract
        except (AttributeError, MissingTokenMetadata):
            log.error(f'Failed to find a contract for "{symbol}" in Coin objects nor default_contracts...')
            raise MissingTokenMetadata(f"Couldn't find '{symbol}' contract in DB coin settings or default_contracts.")
