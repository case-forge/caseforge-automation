"use client";

import { bytesLabel } from "@/lib/systemStatus";
import { shareLabel, type PieSlice } from "@/lib/storageStatus";

const RADIUS = 15.9155;
const SIZE = 42;

export function StoragePie({ slices }: { slices: PieSlice[] }) {
  const total = slices.reduce((n, s) => n + s.bytes, 0);
  let offset = 0;
  return (
    <div className="storage-pie">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="storage-pie-svg" role="img" aria-label={`Space used across the cloud drives: ${bytesLabel(total)} in all`}>
        <circle className="storage-pie-track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" strokeWidth="6" />
        {slices.map((s) => {
          const length = s.fraction * 100;
          const circle = (
            <circle
              key={s.key}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              strokeWidth="6"
              strokeDasharray={`${length} ${100 - length}`}
              strokeDashoffset={-offset}
              style={{ stroke: s.colour }}
              transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            />
          );
          offset += length;
          return circle;
        })}
        <text x={SIZE / 2} y={SIZE / 2 - 0.5} className="storage-pie-total" textAnchor="middle">
          {bytesLabel(total)}
        </text>
        <text x={SIZE / 2} y={SIZE / 2 + 3.5} className="storage-pie-caption" textAnchor="middle">
          in the cloud
        </text>
      </svg>
      <table className="storage-pie-table">
        <caption className="storage-sr-only">Cloud storage by place</caption>
        <thead>
          <tr>
            <th scope="col">Place</th>
            <th scope="col">Size</th>
            <th scope="col">Share</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((s) => (
            <tr key={s.key}>
              <th scope="row">
                <span className="storage-swatch" style={{ background: s.colour }} aria-hidden="true" />
                {s.label}
              </th>
              <td>{bytesLabel(s.bytes)}</td>
              <td>{shareLabel(s.fraction)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
