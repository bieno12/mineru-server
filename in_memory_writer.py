from magic_pdf.data.data_reader_writer import DataWriter
from typing import List, Dict, Optional

class InMemoryDataWriter(DataWriter):
    """An in-memory implementation of DataWriter that stores data in a dictionary."""
    
    def __init__(self):
        self._storage: Dict[str, bytes] = {}
    
    def write(self, path: str, data: bytes) -> None:
        """Write the data to the in-memory storage.

        Args:
            path (str): the target file path (used as key)
            data (bytes): the data to write
        """
        self._storage[path] = data
    
    def read(self, path: str) -> Optional[bytes]:
        """Read data from the in-memory storage.

        Args:
            path (str): the file path to read from

        Returns:
            Optional[bytes]: the data if found, None otherwise
        """
        return self._storage.get(path)
    
    def read_string(self, path: str, encoding: str = 'utf-8') -> Optional[str]:
        """Read data as string from the in-memory storage.

        Args:
            path (str): the file path to read from
            encoding (str): the encoding to use for decoding

        Returns:
            Optional[str]: the decoded string if found, None otherwise
        """
        data = self.read(path)
        if data is not None:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                return data.decode(encoding, errors='replace')
        return None
    
    def exists(self, path: str) -> bool:
        """Check if a file exists in the in-memory storage.

        Args:
            path (str): the file path to check

        Returns:
            bool: True if the file exists, False otherwise
        """
        return path in self._storage
    
    def list_files(self) -> list[str]:
        """List all file paths in the in-memory storage.

        Returns:
            list[str]: list of all file paths
        """
        return list(self._storage.keys())
    
    def delete(self, path: str) -> bool:
        """Delete a file from the in-memory storage.

        Args:
            path (str): the file path to delete

        Returns:
            bool: True if the file was deleted, False if it didn't exist
        """
        if path in self._storage:
            del self._storage[path]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all data from the in-memory storage."""
        self._storage.clear()
    
    def size(self) -> int:
        """Get the number of files in the storage.

        Returns:
            int: number of files stored
        """
        return len(self._storage)
