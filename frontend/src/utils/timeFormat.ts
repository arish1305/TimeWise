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
