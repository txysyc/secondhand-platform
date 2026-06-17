import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helper?: string;
  error?: string;
  required?: boolean;
  icon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, helper, error, required, icon, className = '', type, ...props }, ref) => {
    const [showPassword, setShowPassword] = useState(false);
    const isPassword = type === 'password';
    const inputType = isPassword ? (showPassword ? 'text' : 'password') : type;

    const inputClasses = [
      'form-control',
      error ? 'is-invalid' : '',
      icon ? 'has-icon' : '',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div className="form-group">
        {label && (
          <label htmlFor={props.id} className={required ? 'form-label-required' : ''}>
            {label}
          </label>
        )}
        <div className={icon || isPassword ? 'input-with-icon' : undefined}>
          {icon && <span className="input-icon">{icon}</span>}
          <input ref={ref} type={inputType} className={inputClasses} {...props} />
          {isPassword && (
            <span className="input-suffix">
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                tabIndex={-1}
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          )}
        </div>
        {error && <span className="invalid-feedback">{error}</span>}
        {helper && !error && <span className="form-helper">{helper}</span>}
      </div>
    );
  }
);

Input.displayName = 'Input';
