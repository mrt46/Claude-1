"""
Binance Exchange API Wrapper.

Handles authenticated API calls for trading operations.
"""

import hashlib
import hmac
import time
from typing import Dict, List, Optional

import aiohttp

from src.core.logger import get_logger
from src.core.rate_limiter import get_rate_limiter

logger = get_logger(__name__)


class BinanceExchange:
    """
    Binance exchange API wrapper for trading operations.
    
    Handles:
    - Account information
    - Order placement
    - Order status
    - Balance queries
    """
    
    BASE_URL = "https://api.binance.com/api/v3"
    TESTNET_URL = "https://testnet.binance.vision/api/v3"
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initialize Binance exchange client.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet endpoint
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.testnet = testnet
        
        # Time synchronization attributes
        self.time_offset_ms: int = 0  # Milliseconds offset between local and server time
        self.last_sync_time: float = 0.0  # Unix timestamp of last sync
        self.sync_interval: int = 3600  # Re-sync every hour (in seconds)
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        # Sync server time on startup
        try:
            await self.sync_server_time()
        except Exception as e:
            logger.warning(f"Failed to sync server time on startup: {e}. Will retry on first API call.")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def sync_server_time(self) -> None:
        """
        Sync with Binance server time.
        
        Algorithm:
        1. Measure local time before request (t1)
        2. Get server time from Binance
        3. Measure local time after request (t2)
        4. Calculate latency = (t2 - t1) / 2
        5. Calculate offset = server_time - (t1 + latency)
        
        This ensures timestamps account for network latency and clock drift.
        
        Raises:
            RuntimeError: If session not initialized
            aiohttp.ClientError: If API call fails
            
        Example:
            >>> async with exchange:
            ...     await exchange.sync_server_time()
            ...     timestamp = exchange.get_timestamp()
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized. Use async context manager.")
        
        url = f"{self.base_url}/time"
        
        try:
            # Measure local time before request
            t1_ms = int(time.time() * 1000)
            
            async with self.session.get(url) as response:
                response.raise_for_status()
                server_data = await response.json()
            
            # Measure local time after request
            t2_ms = int(time.time() * 1000)
            
            # Calculate latency (round-trip time / 2)
            latency_ms = (t2_ms - t1_ms) // 2
            
            # Get server time
            server_time_ms = int(server_data.get('serverTime', 0))
            
            if server_time_ms == 0:
                raise ValueError("Invalid server time response")
            
            # Calculate offset: server_time - (local_time_at_request + latency)
            # We use t1 + latency as the best estimate of when the server processed the request
            estimated_local_time_ms = t1_ms + latency_ms
            self.time_offset_ms = server_time_ms - estimated_local_time_ms
            
            # Update last sync time
            self.last_sync_time = time.time()
            
            logger.info(
                f"Server time synced: offset={self.time_offset_ms}ms, "
                f"latency={latency_ms}ms, server_time={server_time_ms}"
            )
            
            # Log warning if offset is large
            if abs(self.time_offset_ms) > 1000:
                logger.warning(
                    f"Large time offset detected: {self.time_offset_ms}ms. "
                    f"Consider syncing system clock."
                )
        
        except aiohttp.ClientError as e:
            logger.error(f"Error syncing server time: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error syncing server time: {e}")
            raise
    
    def get_timestamp(self) -> int:
        """
        Get Binance-compatible timestamp with server time offset applied.
        
        Returns:
            Timestamp in milliseconds: local_time_ms + time_offset_ms
            
        Example:
            >>> timestamp = exchange.get_timestamp()
            >>> params = {'timestamp': timestamp, ...}
        """
        local_time_ms = int(time.time() * 1000)
        return local_time_ms + self.time_offset_ms
    
    async def _check_time_sync(self) -> None:
        """
        Check if time synchronization is needed and sync if required.
        
        Re-syncs if:
        - More than sync_interval seconds have passed since last sync
        - Never synced before (last_sync_time == 0)
        
        This is called before each authenticated API request to ensure
        timestamps are always accurate.
        """
        current_time = time.time()
        time_since_sync = current_time - self.last_sync_time
        
        if self.last_sync_time == 0 or time_since_sync >= self.sync_interval:
            logger.debug(f"Time sync needed (last sync: {time_since_sync:.0f}s ago)")
            try:
                await self.sync_server_time()
            except Exception as e:
                logger.warning(f"Failed to sync time: {e}. Using existing offset.")
    
    def _generate_signature(self, params: Dict) -> str:
        """
        Generate HMAC SHA256 signature for authenticated requests.
        
        Args:
            params: Request parameters
        
        Returns:
            Signature string
        """
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def get_account_info(self) -> Dict:
        """
        Get account information.

        Returns:
            Account information dictionary

        Raises:
            RuntimeError: If session not initialized
            ValueError: If timestamp error (-1021) occurs and re-sync fails
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized. Use async context manager.")

        # Rate limiting (weight=10 for account endpoint)
        rate_limiter = get_rate_limiter()
        await rate_limiter.wait_if_needed(weight=10)

        # Check and sync time if needed
        await self._check_time_sync()
        
        params = {
            'timestamp': self.get_timestamp()
        }
        params['signature'] = self._generate_signature(params)
        
        url = f"{self.base_url}/account"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                # Handle timestamp error (-1021)
                if response.status == 400:
                    error_data = await response.json()
                    error_code = error_data.get('code', 0)
                    
                    if error_code == -1021:
                        logger.warning("Timestamp error (-1021) detected, re-syncing time...")
                        await self.sync_server_time()
                        
                        # Retry with new timestamp
                        params['timestamp'] = self.get_timestamp()
                        params['signature'] = self._generate_signature(params)
                        
                        async with self.session.get(url, params=params, headers=headers) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching account info: {e}")
            raise
    
    async def get_balance(self, asset: str = "USDT") -> float:
        """
        Get balance for a specific asset.
        
        Args:
            asset: Asset symbol (e.g., "USDT", "BTC")
        
        Returns:
            Available balance
        """
        account_info = await self.get_account_info()
        
        for balance in account_info.get('balances', []):
            if balance['asset'] == asset:
                return float(balance['free'])
        
        return 0.0
    
    async def place_order(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        order_type: str,  # 'MARKET' or 'LIMIT'
        quantity: Optional[float] = None,
        quote_order_qty: Optional[float] = None,  # For market orders
        price: Optional[float] = None,  # For limit orders
        time_in_force: str = "GTC"  # GTC, IOC, FOK
    ) -> Dict:
        """
        Place an order.

        Args:
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            order_type: 'MARKET' or 'LIMIT'
            quantity: Order quantity (base asset)
            quote_order_qty: Order quantity in quote asset (for market orders)
            price: Limit price (required for limit orders)
            time_in_force: Time in force (GTC, IOC, FOK)

        Returns:
            Order response dictionary

        Raises:
            RuntimeError: If session not initialized
            ValueError: If order parameters are invalid or order fails
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized.")

        # Rate limiting for order requests (weight=1, is_order=True)
        rate_limiter = get_rate_limiter()
        await rate_limiter.wait_if_needed(weight=1, is_order=True)

        # Check and sync time if needed
        await self._check_time_sync()
        
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': order_type.upper(),
            'timestamp': self.get_timestamp()
        }
        
        if order_type.upper() == 'LIMIT':
            if price is None:
                raise ValueError("Price required for limit orders")
            params['price'] = str(price)
            params['timeInForce'] = time_in_force
        
        if quantity:
            params['quantity'] = str(quantity)
        elif quote_order_qty:
            params['quoteOrderQty'] = str(quote_order_qty)
        else:
            raise ValueError("Either quantity or quote_order_qty must be provided")
        
        params['signature'] = self._generate_signature(params)
        
        url = f"{self.base_url}/order"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        try:
            async with self.session.post(url, params=params, headers=headers) as response:
                if response.status == 400:
                    error_data = await response.json()
                    error_code = error_data.get('code', 0)
                    error_msg = error_data.get('msg', 'Unknown error')
                    
                    # Handle timestamp error (-1021)
                    if error_code == -1021:
                        logger.warning("Timestamp error (-1021) detected, re-syncing time and retrying...")
                        await self.sync_server_time()
                        
                        # Retry with new timestamp
                        params['timestamp'] = self.get_timestamp()
                        params['signature'] = self._generate_signature(params)
                        
                        async with self.session.post(url, params=params, headers=headers) as retry_response:
                            if retry_response.status == 400:
                                retry_error_data = await retry_response.json()
                                logger.error(f"Order placement failed after re-sync: {retry_error_data}")
                                raise ValueError(f"Order placement failed: {retry_error_data.get('msg', 'Unknown error')}")
                            
                            retry_response.raise_for_status()
                            order_data = await retry_response.json()
                            logger.info(f"Order placed (after re-sync): {order_data.get('orderId')} - {symbol} {side} {quantity}")
                            return order_data
                    else:
                        logger.error(f"Order placement failed: {error_data}")
                        raise ValueError(f"Order placement failed: {error_msg}")
                
                response.raise_for_status()
                order_data = await response.json()
                logger.info(f"Order placed: {order_data.get('orderId')} - {symbol} {side} {quantity}")
                return order_data
        except aiohttp.ClientError as e:
            logger.error(f"Error placing order: {e}")
            raise
    
    async def get_order_status(self, symbol: str, order_id: int) -> Dict:
        """
        Get order status.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
        
        Returns:
            Order status dictionary
            
        Raises:
            RuntimeError: If session not initialized
            ValueError: If timestamp error (-1021) occurs and re-sync fails
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized.")
        
        # Check and sync time if needed
        await self._check_time_sync()
        
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id,
            'timestamp': self.get_timestamp()
        }
        params['signature'] = self._generate_signature(params)
        
        url = f"{self.base_url}/order"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                # Handle timestamp error (-1021)
                if response.status == 400:
                    error_data = await response.json()
                    error_code = error_data.get('code', 0)
                    
                    if error_code == -1021:
                        logger.warning("Timestamp error (-1021) detected, re-syncing time...")
                        await self.sync_server_time()
                        
                        # Retry with new timestamp
                        params['timestamp'] = self.get_timestamp()
                        params['signature'] = self._generate_signature(params)
                        
                        async with self.session.get(url, params=params, headers=headers) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching order status: {e}")
            raise
    
    async def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """
        Cancel an order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
        
        Returns:
            Cancellation response
            
        Raises:
            RuntimeError: If session not initialized
            ValueError: If timestamp error (-1021) occurs and re-sync fails
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized.")
        
        # Check and sync time if needed
        await self._check_time_sync()
        
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id,
            'timestamp': self.get_timestamp()
        }
        params['signature'] = self._generate_signature(params)
        
        url = f"{self.base_url}/order"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        try:
            async with self.session.delete(url, params=params, headers=headers) as response:
                # Handle timestamp error (-1021)
                if response.status == 400:
                    error_data = await response.json()
                    error_code = error_data.get('code', 0)
                    
                    if error_code == -1021:
                        logger.warning("Timestamp error (-1021) detected, re-syncing time...")
                        await self.sync_server_time()
                        
                        # Retry with new timestamp
                        params['timestamp'] = self.get_timestamp()
                        params['signature'] = self._generate_signature(params)
                        
                        async with self.session.delete(url, params=params, headers=headers) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Error canceling order: {e}")
            raise
    
    async def get_ticker_price(self, symbol: str) -> Optional[float]:
        """
        Get current ticker price for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT', 'BNBUSDT')
        
        Returns:
            Current price or None if error
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized.")
        
        url = f"{self.base_url}/ticker/price"
        params = {'symbol': symbol.upper()}
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 400:
                    error_data = await response.json()
                    logger.warning(f"Price fetch failed for {symbol}: {error_data.get('msg', 'Unknown error')}")
                    return None
                response.raise_for_status()
                data = await response.json()
                return float(data.get('price', 0))
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None
    
    async def get_all_balances(self) -> List[Dict]:
        """
        Get all non-zero balances from account.
        
        Returns:
            List of balance dictionaries:
            [
                {'asset': 'BTC', 'free': 0.05, 'locked': 0.0},
                {'asset': 'ETH', 'free': 2.5, 'locked': 0.0},
                ...
            ]
        """
        try:
            account_info = await self.get_account_info()
            balances = []
            
            for balance in account_info.get('balances', []):
                free = float(balance.get('free', 0))
                locked = float(balance.get('locked', 0))
                total = free + locked
                
                # Only include non-zero balances
                if total > 0:
                    balances.append({
                        'asset': balance['asset'],
                        'free': free,
                        'locked': locked,
                        'total': total
                    })
            
            return balances
        except Exception as e:
            logger.error(f"Error fetching all balances: {e}")
            return []
    
    async def get_balance_in_usdt(self, asset: str) -> float:
        """
        Get balance value in USDT.
        
        Args:
            asset: Asset symbol (e.g., 'BTC', 'ETH', 'BNB')
        
        Returns:
            Value in USDT, or 0.0 if error or asset is USDT
        """
        if asset == 'USDT':
            balance = await self.get_balance('USDT')
            return balance
        
        try:
            # Get balance
            balance = await self.get_balance(asset)
            if balance == 0:
                return 0.0
            
            # Get price
            symbol = f"{asset}USDT"
            price = await self.get_ticker_price(symbol)
            
            if price is None:
                logger.warning(f"Could not get price for {symbol}, returning 0")
                return 0.0
            
            return balance * price
        except Exception as e:
            logger.error(f"Error calculating USDT value for {asset}: {e}")
            return 0.0
    
    async def get_order_book(self, symbol: str, limit: int = 5) -> Dict:
        """
        Get order book snapshot.
        
        Args:
            symbol: Trading symbol
            limit: Number of levels (5, 10, 20, 50, 100, 500, 1000)
        
        Returns:
            Order book dictionary with 'bids' and 'asks' arrays
        """
        if not self.session:
            raise RuntimeError("Exchange client not initialized.")
        
        url = f"{self.base_url}/depth"
        params = {
            'symbol': symbol.upper(),
            'limit': limit
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    'bids': data.get('bids', []),
                    'asks': data.get('asks', []),
                    'lastUpdateId': data.get('lastUpdateId', 0)
                }
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching order book for {symbol}: {e}")
            raise
    
    async def get_portfolio_summary(self) -> Dict:
        """
        Get complete portfolio summary with all balances and USDT values.
        
        Returns:
            Dictionary containing:
            {
                'total_value_usdt': float,
                'balances': [
                    {
                        'asset': str,
                        'free': float,
                        'locked': float,
                        'total': float,
                        'value_usdt': float
                    },
                    ...
                ],
                'bnb_value_usdt': float,
                'usdt_balance': float
            }
        """
        try:
            # Get all balances
            balances = await self.get_all_balances()
            
            # Get USDT balance
            usdt_balance = await self.get_balance('USDT')
            
            # Calculate USDT values for each asset
            portfolio_balances = []
            total_value = usdt_balance
            bnb_value_usdt = 0.0
            
            for balance in balances:
                asset = balance['asset']
                
                if asset == 'USDT':
                    value_usdt = balance['free']
                else:
                    value_usdt = await self.get_balance_in_usdt(asset)
                
                portfolio_balances.append({
                    'asset': asset,
                    'free': balance['free'],
                    'locked': balance['locked'],
                    'total': balance['total'],
                    'value_usdt': value_usdt
                })
                
                total_value += value_usdt
                
                if asset == 'BNB':
                    bnb_value_usdt = value_usdt
            
            # Sort by value (descending)
            portfolio_balances.sort(key=lambda x: x['value_usdt'], reverse=True)
            
            return {
                'total_value_usdt': total_value,
                'balances': portfolio_balances,
                'bnb_value_usdt': bnb_value_usdt,
                'usdt_balance': usdt_balance
            }
        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return {
                'total_value_usdt': 0.0,
                'balances': [],
                'bnb_value_usdt': 0.0,
                'usdt_balance': 0.0
            }