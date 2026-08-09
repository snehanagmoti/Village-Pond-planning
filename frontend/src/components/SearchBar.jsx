import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API_URL = "http://localhost:8000/api/search-village";

/**
 * SearchBar component — geocodes village names using Nominatim via the backend.
 * Displays a dropdown of matching results for the user to select.
 */
export default function SearchBar({ onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const containerRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSearch = (value) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (value.trim().length < 2) {
      setResults([]);
      setShowDropdown(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const resp = await axios.get(API_URL, { params: { q: value } });
        setResults(resp.data || []);
        setShowDropdown(true);
      } catch (err) {
        console.error("Search error:", err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 400); // 400ms debounce to respect Nominatim rate limits
  };

  const handleSelect = (result) => {
    setQuery(result.display_name.split(',')[0]); // Show short name
    setShowDropdown(false);
    onSelect(result);
  };

  return (
    <div className="search-container" ref={containerRef}>
      <div className="search-input-wrapper">
        <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8"/>
          <path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          id="village-search"
          type="text"
          placeholder="Search village or location..."
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          onFocus={() => results.length > 0 && setShowDropdown(true)}
          autoComplete="off"
        />
        {loading && <div className="search-spinner"></div>}
      </div>

      {showDropdown && results.length > 0 && (
        <ul className="search-dropdown">
          {results.map((r, idx) => (
            <li key={idx} onClick={() => handleSelect(r)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                <circle cx="12" cy="10" r="3"/>
              </svg>
              <span>{r.display_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
