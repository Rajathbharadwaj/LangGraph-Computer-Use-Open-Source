"""
Cookie encryption service for secure storage
"""
import os
import json
from cryptography.fernet import Fernet
from typing import List, Dict

class CookieEncryptionService:
    """
    Encrypts and decrypts X cookies for secure storage
    """
    
    def __init__(self):
        # Get encryption key from environment
        key = os.getenv("COOKIE_ENCRYPTION_KEY")
        
        if not key:
            # Generate a new key if not provided (dev only!)
            print("⚠️  WARNING: No COOKIE_ENCRYPTION_KEY found, generating new one")
            print("⚠️  This should NEVER happen in production!")
            key = Fernet.generate_key().decode()
            print(f"⚠️  Generated key: {key}")
            print("⚠️  Add this to your .env file!")
        
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
    
    def encrypt_cookies(self, cookies: List[Dict]) -> str:
        """
        Encrypt a list of cookies
        
        Args:
            cookies: List of cookie dictionaries
            
        Returns:
            Encrypted string
        """
        try:
            # Convert to JSON
            cookies_json = json.dumps(cookies)
            
            # Encrypt
            encrypted = self.cipher.encrypt(cookies_json.encode())
            
            return encrypted.decode()
        except Exception as e:
            print(f"❌ Error encrypting cookies: {e}")
            raise
    
    def decrypt_cookies(self, encrypted_cookies: str) -> List[Dict]:
        """
        Decrypt cookies
        
        Args:
            encrypted_cookies: Encrypted cookie string
            
        Returns:
            List of cookie dictionaries
        """
        try:
            # Decrypt
            decrypted = self.cipher.decrypt(encrypted_cookies.encode())
            
            # Parse JSON
            cookies = json.loads(decrypted.decode())
            
            return cookies
        except Exception as e:
            print(f"❌ Error decrypting cookies: {e}")
            raise
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key
        
        Returns:
            Base64-encoded encryption key
        """
        return Fernet.generate_key().decode()


# Global instance
cookie_encryption = CookieEncryptionService()

