"""
Bambu Lab HTTP API Client
==========================

Provides a unified interface for interacting with the Bambu Lab Cloud API.
"""

import requests
import json
from typing import Dict, Any, Optional, List


class BambuAPIError(Exception):
    """Base exception for Bambu API errors"""
    pass


class BambuClient:
    """
    HTTP client for Bambu Lab Cloud API.
    
    Handles authentication, request formatting, and response parsing.
    """
    
    BASE_URL = "https://api.bambulab.com"
    DEFAULT_TIMEOUT = 30
    
    def __init__(self, token: str, timeout: int = None):
        """
        Initialize the Bambu API client.
        
        Args:
            token: Bambu Lab access token
            timeout: Request timeout in seconds (default: 30)
        """
        self.token = token
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.session = requests.Session()
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        **kwargs
    ) -> Any:
        """
        Make an API request.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (relative to BASE_URL)
            params: Query parameters
            data: Request body data
            **kwargs: Additional arguments passed to requests
        
        Returns:
            Parsed JSON response
            
        Raises:
            BambuAPIError: If request fails
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = self._get_headers()
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                timeout=kwargs.get('timeout', self.timeout)
            )
            
            # Check for errors
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', response.text)
                except:
                    error_msg = response.text
                raise BambuAPIError(
                    f"API request failed ({response.status_code}): {error_msg}"
                )
            
            # Parse response
            if response.content:
                return response.json()
            return None
            
        except requests.exceptions.RequestException as e:
            raise BambuAPIError(f"Request failed: {e}")
    
    def get(self, endpoint: str, params: Optional[Dict] = None, **kwargs) -> Any:
        """Make a GET request"""
        return self._request('GET', endpoint, params=params, **kwargs)
    
    def post(self, endpoint: str, data: Optional[Dict] = None, **kwargs) -> Any:
        """Make a POST request"""
        return self._request('POST', endpoint, data=data, **kwargs)
    
    def put(self, endpoint: str, data: Optional[Dict] = None, **kwargs) -> Any:
        """Make a PUT request"""
        return self._request('PUT', endpoint, data=data, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> Any:
        """Make a DELETE request"""
        return self._request('DELETE', endpoint, **kwargs)
    
    # ===== Device Management =====
    
    def get_devices(self) -> List[Dict]:
        """
        Get list of bound devices.
        
        Returns:
            List of device dictionaries
        """
        response = self.get('v1/iot-service/api/user/bind')
        return response.get('devices', [])
    
    def get_device_version(self, device_id: str) -> Dict:
        """
        Get firmware version info for a device.
        
        Args:
            device_id: Device serial number
            
        Returns:
            Version information dictionary
        """
        return self.get('v1/iot-service/api/user/device/version', 
                       params={'dev_id': device_id})
    
    def get_device_versions(self) -> Dict:
        """
        Get firmware versions for all devices.
        
        Alias for get_device_version without device_id parameter.
        Returns version information for all user devices.
        
        Returns:
            Version information dictionary
        """
        return self.get('v1/iot-service/api/user/device/version')
    
    def get_ams_filaments(self, device_id: str) -> Dict:
        """
        Get AMS (Automatic Material System) filament information.
        
        Returns detailed information about AMS units, trays, and loaded filaments.
        
        Args:
            device_id: Device serial number
            
        Returns:
            Dictionary with AMS units, trays, and filament data
        
        Example:
            >>> ams_info = client.get_ams_filaments("01P00A123456789")
            >>> for unit in ams_info.get('ams_units', []):
            ...     print(f"AMS Unit {unit['unit_id']}:")
            ...     for tray in unit.get('trays', []):
            ...         print(f"  Tray {tray['tray_id']}: {tray.get('filament_type')}")
        """
        version = self.get_device_version(device_id)
        
        result = {
            'device_id': device_id,
            'ams_units': [],
            'total_trays': 0,
            'has_ams': False
        }
        
        # Extract AMS info from version data
        if 'devices' in version:
            for dev in version['devices']:
                if dev.get('dev_id') == device_id:
                    if 'ams' in dev:
                        result['has_ams'] = True
                        ams_list = dev['ams'] if isinstance(dev['ams'], list) else [dev['ams']]
                        
                        for idx, ams in enumerate(ams_list):
                            unit_info = {
                                'unit_id': idx,
                                'sw_version': ams.get('sw_ver'),
                                'hw_version': ams.get('hw_ver'),
                                'trays': [],
                                'raw_data': ams
                            }
                            
                            # Extract tray/filament info if available
                            if 'tray' in ams:
                                trays = ams['tray'] if isinstance(ams['tray'], list) else [ams['tray']]
                                for tray in trays:
                                    tray_info = {
                                        'tray_id': tray.get('id', tray.get('tray_id')),
                                        'filament_type': tray.get('tray_type', tray.get('type')),
                                        'filament_color': tray.get('tray_color', tray.get('color')),
                                        'filament_weight': tray.get('tray_weight', tray.get('weight')),
                                        'temperature': tray.get('nozzle_temp_min', tray.get('temp')),
                                        'remaining': tray.get('remain', tray.get('remaining')),
                                        'raw_data': tray
                                    }
                                    unit_info['trays'].append(tray_info)
                                    result['total_trays'] += 1
                            
                            result['ams_units'].append(unit_info)
                    break
        
        return result
    
    def get_print_status(self, force: bool = False) -> Dict:
        """
        Get print status for all devices.
        
        Args:
            force: Force refresh (bypass cache)
            
        Returns:
            Print status dictionary
        """
        params = {'force': 'true' if force else 'false'}
        return self.get('v1/iot-service/api/user/print', params=params)
    
    def start_print_job(
        self,
        device_id: str,
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
        file_url: Optional[str] = None,
        settings: Optional[Dict] = None
    ) -> Dict:
        """
        Start a print job on a device.
        
        Args:
            device_id: Device serial number
            file_id: File ID (if file already uploaded to cloud)
            file_name: Name of the file
            file_url: Direct URL to the file
            settings: Print settings (layer_height, infill, speed, etc.)
            
        Returns:
            Print job information with job_id and status
            
        Example:
            >>> job = client.start_print_job(
            ...     device_id="01P00A123456789",
            ...     file_id="abc123",
            ...     file_name="model.3mf",
            ...     settings={"layer_height": 0.2, "infill": 20}
            ... )
        """
        data = {'device_id': device_id}
        
        if file_id:
            data['file_id'] = file_id
        if file_name:
            data['file_name'] = file_name
        if file_url:
            data['file_url'] = file_url
        if settings:
            data['settings'] = settings
        
        return self.post('v1/iot-service/api/user/print', data=data)
    
    # ===== User Management =====
    
    def get_user_profile(self) -> Dict:
        """
        Get user profile information.
        
        Returns:
            User profile dictionary with name, email, etc.
        """
        return self.get('v1/user-service/my/profile')
    
    def get_user_info(self) -> Dict:
        """
        Get user preference/info from design service.
        
        This includes the user UID needed for MQTT connections.
        
        Returns:
            User info including UID
        """
        return self.get('v1/design-user-service/my/preference')
    
    def update_user_profile(self, data: Dict) -> Dict:
        """
        Update user profile.
        
        Args:
            data: Profile data to update
            
        Returns:
            Updated profile information
        """
        return self.put('v1/user-service/my/profile', data=data)
    
    # ===== Project Management =====
    
    def get_projects(self) -> List[Dict]:
        """
        Get list of projects/files from cloud.
        
        Returns:
            List of project dictionaries with file info
        """
        response = self.get('v1/iot-service/api/user/project')
        return response.get('projects', [])
    
    def get_cloud_files(self) -> List[Dict]:
        """
        Get list of uploaded files from cloud storage.
        
        Tries multiple endpoints to find your uploaded files.
        
        Returns:
            List of file dictionaries with file_id, name, url, etc.
            
        Example:
            >>> files = client.get_cloud_files()
            >>> for f in files:
            ...     print(f"File: {f['name']}, ID: {f['file_id']}")
        """
        # Try projects endpoint
        try:
            projects = self.get_projects()
            files = []
            for project in projects:
                if 'files' in project:
                    files.extend(project['files'])
                elif 'model_id' in project:
                    files.append(project)
            if files:
                return files
        except:
            pass
        
        # Try direct files endpoint
        try:
            response = self.get('v1/iot-service/api/user/files')
            return response.get('files', [])
        except:
            pass
        
        # Try tasks endpoint (may show uploaded files)
        try:
            return self.get_tasks()
        except:
            pass
        
        return []
    
    def create_project(self, name: str, **kwargs) -> Dict:
        """
        Create a new project.
        
        Args:
            name: Project name
            **kwargs: Additional project parameters
            
        Returns:
            Created project information
        """
        data = {'name': name, **kwargs}
        return self.post('v1/iot-service/api/user/project', data=data)
    
    def get_tasks(self) -> List[Dict]:
        """
        Get list of print tasks.
        
        Returns:
            List of task dictionaries
        """
        response = self.get('v1/iot-service/api/user/task')
        return response.get('tasks', response.get('hits', []))
    
    def get_task(self, task_id: str) -> Dict:
        """
        Get details of a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task details dictionary
        """
        return self.get(f'v1/iot-service/api/user/task/{task_id}')
    
    # ===== Camera/Webcam Access =====
    
    def get_camera_credentials(self, device_id: str) -> Dict:
        """
        Get temporary credentials for accessing printer webcam/camera.
        
        Returns ttcode, passwd, and authkey needed to connect to the
        printer's video stream.
        
        Args:
            device_id: Device serial number
            
        Returns:
            Dictionary with 'ttcode', 'passwd', 'authkey' for webcam access
            
        Example:
            >>> credentials = client.get_camera_credentials("01S00A000000000")
            >>> ttcode = credentials['ttcode']
            >>> passwd = credentials['passwd']
            >>> authkey = credentials['authkey']
        """
        data = {'dev_id': device_id}
        return self.post('v1/iot-service/api/user/ttcode', data=data)
    
    def get_ttcode(self, device_id: str) -> Dict:
        """
        Alias for get_camera_credentials().
        
        Get TTCode for webcam access.
        """
        return self.get_camera_credentials(device_id)
    
    # ===== Device Binding =====
    
    def bind_device(self, device_id: str, device_name: str, bind_code: str) -> Dict:
        """
        Bind a new device to your account.
        
        Args:
            device_id: Device serial number
            device_name: Friendly name for the device
            bind_code: 8-digit bind code from printer
            
        Returns:
            Bind result dictionary
            
        Example:
            >>> result = client.bind_device(
            ...     device_id="01P00A123456789",
            ...     device_name="My P1S",
            ...     bind_code="12345678"
            ... )
        """
        data = {
            'device_id': device_id,
            'device_name': device_name,
            'bind_code': bind_code
        }
        return self.post('v1/iot-service/api/user/bind', data=data)
    
    def unbind_device(self, device_id: str) -> Dict:
        """
        Unbind a device from your account.
        
        Args:
            device_id: Device serial number
            
        Returns:
            Unbind result dictionary
        """
        return self.delete('v1/iot-service/api/user/bind', params={'dev_id': device_id})
    
    def get_device_info(self, device_id: str) -> Dict:
        """
        Get detailed information about a specific device.
        
        Args:
            device_id: Device serial number
            
        Returns:
            Device information dictionary
        """
        return self.get('v1/iot-service/api/user/device/info', params={'device_id': device_id})
