import { formatTime12Hour, normalizeTimeValue } from '../utils/timeFormat';

type TimePicker12Props = {
    value: string;
    onChange: (value: string) => void;
};

const timeOptions = Array.from({ length: 24 * 12 }, (_, index) => {
    const totalMinutes = index * 5;
    const hour = Math.floor(totalMinutes / 60);
    const minute = totalMinutes % 60;
    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
});

const TimePicker12 = ({ value, onChange }: TimePicker12Props) => {
    const normalizedValue = normalizeTimeValue(value);
    const options = timeOptions.includes(normalizedValue)
        ? timeOptions
        : [...timeOptions, normalizedValue].sort();

    return (
        <select
            className="input-field"
            value={normalizedValue}
            onChange={(event) => onChange(event.target.value)}
            aria-label="Time"
            style={{ width: '100%', minWidth: 128, whiteSpace: 'nowrap' }}
        >
            {options.map((option) => (
                <option key={option} value={option}>{formatTime12Hour(option)}</option>
            ))}
        </select>
    );
};

export default TimePicker12;
