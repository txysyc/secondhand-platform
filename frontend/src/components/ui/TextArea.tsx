import React from 'react';

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helper?: string;
  error?: string;
  required?: boolean;
}

export const TextArea = React.forwardRef<HTMLTextAreaElement, TextAreaProps>(
  ({ label, helper, error, required, className = '', ...props }, ref) => {
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
        <textarea ref={ref} className={classes} {...props} />
        {error && <span className="invalid-feedback">{error}</span>}
        {helper && !error && <span className="form-helper">{helper}</span>}
      </div>
    );
  }
);

TextArea.displayName = 'TextArea';
