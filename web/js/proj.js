// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// South polar stereographic projection on a sphere (CONTRACT §2: spherical Moon, R = 1,737,400 m,
// lat_0 = -90, lon_0 = 0, true scale at the pole). Parameters are read from /api/meta map.crs_proj4.
//   forward: rho = 2 R k0 tan(pi/4 + lat/2),  x = x0 + rho sin(lon - lon0),  y = y0 + rho cos(lon - lon0)
//   inverse: lat = 2 atan(rho / (2 R k0)) - pi/2,  lon = lon0 + atan2(x - x0, y - y0)

const DEG = Math.PI / 180;
const DEFAULT = { R: 1737400, lat0: -90, lon0: 0, x0: 0, y0: 0, k0: 1 };

/** Parse the parameters LunaScout needs from a proj4 string; null if it is not a south polar stereographic sphere. */
export function parseProj4(str) {
  if (!str) return { ...DEFAULT };
  const get = (k) => {
    const m = new RegExp(`\\+${k}=([-+0-9.eE]+)`).exec(str);
    return m ? Number(m[1]) : undefined;
  };
  if (!/\+proj=stere\b/.test(str)) return null;
  const p = {
    R: get("R") ?? get("a") ?? DEFAULT.R,
    lat0: get("lat_0") ?? DEFAULT.lat0,
    lon0: get("lon_0") ?? DEFAULT.lon0,
    x0: get("x_0") ?? 0,
    y0: get("y_0") ?? 0,
    k0: get("k_0") ?? get("k") ?? 1,
  };
  const latTs = get("lat_ts");
  if (p.lat0 !== -90 || (latTs !== undefined && latTs !== -90)) return null;
  return p;
}

export class SouthPolarStereo {
  constructor(proj4) {
    const p = parseProj4(proj4);
    if (!p) console.warn("LunaScout: unexpected map CRS, falling back to the contract's south polar stereographic sphere", proj4);
    Object.assign(this, p || DEFAULT);
  }

  /** Map metres → [lat, lon] degrees (lon in [-180, 180]). */
  toLatLon(x, y) {
    const dx = x - this.x0, dy = y - this.y0;
    const rho = Math.hypot(dx, dy);
    const lat = (2 * Math.atan(rho / (2 * this.R * this.k0)) - Math.PI / 2) / DEG;
    let lon = this.lon0 + Math.atan2(dx, dy) / DEG;
    lon = ((lon + 180) % 360 + 360) % 360 - 180;
    return [lat, lon];
  }

  /** [lat, lon] degrees → map metres [x, y]. */
  toXY(lat, lon) {
    const rho = 2 * this.R * this.k0 * Math.tan(Math.PI / 4 + (lat * DEG) / 2);
    const a = (lon - this.lon0) * DEG;
    return [this.x0 + rho * Math.sin(a), this.y0 + rho * Math.cos(a)];
  }
}
