import { useTilt } from "../lib/tilt.js";

// A glass panel that leans toward the cursor. `as` lets it be a section,
// article, form, whatever the markup needs.
export default function TiltCard({ as: Tag = "div", className = "", max = 5, children, ...rest }) {
  const ref = useTilt(max);
  return (
    <Tag ref={ref} className={`glass tilt ${className}`} {...rest}>
      {children}
    </Tag>
  );
}
