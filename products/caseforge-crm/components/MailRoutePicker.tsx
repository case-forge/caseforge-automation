"use client";

export function MailRoutePicker({
  routes,
  value,
  onChange,
  legend,
  name,
  otherText = "",
  onOtherText,
}: {
  routes: string[];
  value: string;
  onChange: (route: string) => void;
  legend: string;
  name: string;

  otherText?: string;
  onOtherText?: (text: string) => void;
}) {
  return (
    <fieldset className="review-mail-picker">
      <legend>{legend}</legend>
      <div className="review-mail-routes">
        {routes.map((route) => (
          <label key={route}>
            <input type="radio" name={name} value={route} checked={value === route} onChange={() => onChange(route)} />
            {route}
          </label>
        ))}
      </div>
      {value === "Other" && onOtherText && (
        <label className="review-mail-other">
          Where does it go?
          <input type="text" value={otherText} maxLength={80} onChange={(e) => onOtherText(e.target.value)} placeholder="Type the folder or person" />
        </label>
      )}
    </fieldset>
  );
}
