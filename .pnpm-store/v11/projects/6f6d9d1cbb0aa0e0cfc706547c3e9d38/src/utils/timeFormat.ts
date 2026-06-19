export const formatTime12Hour = (time?: string | null, fallback = '-') => {
    if (!time) return fallback;

    const timePart = time.includes('T')
        ? time.split('T')[1]
        : time;
    const [hourValue, minuteValue = '00'] = timePart.split(':');
    const hour = Number(hourValue);

    if (!Number.isFinite(hour)) return fallback;

    const minute = minuteValue.padStart(2, '0').slice(0, 2);
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;

    return `${displayHour}:${minute} ${period}`;
};

export const formatTimeRange12Hour = (
    start?: string | null,
    end?: string | null,
    fallback = '-'
) => {
    if (!start || !end) return fallback;
    return `${formatTime12Hour(start, fallback)} - ${formatTime12Hour(end, fallback)}`;
};

export type TimePeriod = 'AM' | 'PM';

export const normalizeTimeValue = (time?: string | null, fallback = '09:00') => {
    if (!time) return fallback;

    const timePart = time.includes('T')
        ? time.split('T')[1]
        : time;
    const [hourValue, minuteValue = '00'] = timePart.split(':');
    const hour = Number(hourValue);
    const minute = Number(minuteValue);

    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fallback;

    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
};

export const getTime12HourParts = (time?: string | null) => {
    const normalized = normalizeTimeValue(time);
    const [hourValue, minuteValue] = normalized.split(':');
    const hour24 = Number(hourValue);
    const period: TimePeriod = hour24 >= 12 ? 'PM' : 'AM';
    const hour12 = hour24 % 12 || 12;

    return {
        hour: String(hour12),
        minute: minuteValue,
        period,
    };
};

export const buildTimeFrom12HourParts = (
    hour: string | number,
    minute: string | number,
    period: TimePeriod
) => {
    const hourNumber = Number(hour);
    let hour24 = hourNumber % 12;
    if (period === 'PM') {
        hour24 += 12;
    }

    return `${String(hour24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
};
