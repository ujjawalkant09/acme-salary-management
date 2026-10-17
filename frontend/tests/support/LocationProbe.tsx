import { useLocation } from 'react-router'

/** Shows the current URL so tests can check what the router did. */
export function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}
