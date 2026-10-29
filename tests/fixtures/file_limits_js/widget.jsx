export default function Widget({ title }) {
  const onClick = () => {
    console.log(title);
  };
  return (
    <button onClick={onClick}>
      {title}
    </button>
  );
}
