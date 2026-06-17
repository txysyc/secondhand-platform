import React from 'react';

interface SelectOption {
  value: string | number;
  label: string;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  helper?: string;
  error?: string;
  required?: boolean;
  options: SelectOption[];
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, helper, error, required, options, className = '', ...props }, ref) => {
    const classes = ['form-control', error ? 'is-invalid' : '', className]
      .filter(Boolean)
      .join(' ');

    return (
      <div className="form-group">
        {label && (
          <label htmlFor={props.id} className={required ? 'form-label-required' : ''}>
            {label}
          </label>
        )}
        <select ref={ref} className={classes} {...props}>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && <span className="invalid-feedback">{error}</span>}
        {helper && !error && <span className="form-helper">{helper}</span>}
      </div>
    );
  }
);

Select.displayName = 'Select';
