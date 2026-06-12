import { buildTimeFrom12HourParts, getTime12HourParts, type TimePeriod } from '../utils/timeFormat';

type TimePicker12Props = {
    value: string;
    onChange: (value: string) => void;
};

const hourOptions = Array.from({ length: 12 }, (_, index) => String(index + 1));
const baseMinuteOptions = Array.from({ length: 12 }, (_, index) => String(index * 5).padStart(2, '0'));
const periodOptions: TimePeriod[] = ['AM', 'PM'];

const TimePicker12 = ({ value, onChange }: TimePicker12Props) => {
    const parts = getTime12HourParts(value);
    const minuteOptions = baseMinuteOptions.includes(parts.minute)
        ? baseMinuteOptions
        : [...baseMinuteOptions, parts.minute].sort();

    const update = (next: Partial<typeof parts>) => {
        const merged = { ...parts, ...next };
        onChange(buildTimeFrom12HourParts(merged.hour, merged.minute, merged.period));
    };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.4rem' }}>
            <select
                className="input-field"
                value={parts.hour}
                onChange={(event) => update({ hour: event.target.value })}
                aria-label="Hour"
            >
                {hourOptions.map((hour) => (
                    <option key={hour} value={hour}>{hour}</option>
                ))}
            </select>
            <select
                className="input-field"
                value={parts.minute}
                onChange={(event) => update({ minute: event.target.value })}
                aria-label="Minute"
            >
                {minuteOptions.map((minute) => (
                    <option key={minute} value={minute}>{minute}</option>
                ))}
            </select>
            <select
                className="input-field"
                value={parts.period}
                onChange={(event) => update({ period: event.target.value as TimePeriod })}
                aria-label="Period"
            >
                {periodOptions.map((period) => (
                    <option key={period} value={period}>{period}</option>
                ))}
            </select>
        </div>
    );
};

export default TimePicker12;
