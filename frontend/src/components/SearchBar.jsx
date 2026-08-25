import { useEffect, useRef, useState } from 'react';

import { api, apiErrorMessage } from '../api';


export default function SearchBar({ onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const abortRef = useRef(null);

  useEffect(() => () => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const submitSearch = async (event) => {
    event.preventDefault();
    const normalized = query.trim();
    if (normalized.length < 2) {
      setMessage('Enter at least two characters.');
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setMessage('Searching…');
    try {
      const response = await api.get('/search-village', {
        params: { q: normalized },
        signal: controller.signal,
      });
      const nextResults = response.data || [];
      setResults(nextResults);
      setMessage(nextResults.length ? `${nextResults.length} places found.` : 'No matching places found.');
    } catch (error) {
      if (error?.code !== 'ERR_CANCELED') {
        setResults([]);
        setMessage(apiErrorMessage(error, 'Place search failed.'));
      }
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  };

  const chooseResult = (result) => {
    setQuery(result.display_name.split(',')[0]);
    setResults([]);
    setMessage(`${result.display_name} selected.`);
    onSelect(result);
  };

  return (
    <div className="search-container">
      <form className="search-form" onSubmit={submitSearch} role="search">
        <label htmlFor="village-search">Village or location</label>
        <div className="search-input-row">
          <input
            id="village-search"
            type="search"
            placeholder="Example: Ralegan Siddhi"
            value={query}
            minLength={2}
            maxLength={120}
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          <button className="compact-btn" type="submit" disabled={loading}>
            {loading ? 'Searching' : 'Search'}
          </button>
        </div>
      </form>
      <div className="sr-status" aria-live="polite">{message}</div>
      {results.length > 0 && (
        <ul className="search-results" aria-label="Place search results">
          {results.map((result) => (
            <li key={`${result.lat}:${result.lng}:${result.display_name}`}>
              <button type="button" onClick={() => chooseResult(result)}>
                {result.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
