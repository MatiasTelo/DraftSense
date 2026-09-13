/** CA-506 — la definición del concepto medido está a un toque y sale de la base. */

import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { QuestionPrompt } from './QuestionPrompt';

const HELP = { label: 'Engage', text: 'Starting fights on your terms.' };

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <QuestionPrompt
      prompt="Who has more engage?"
      help={HELP}
      open={open}
      onToggle={() => setOpen((value) => !value)}
    />
  );
}

describe('QuestionPrompt', () => {
  it('muestra el enunciado tal como vino, sin componerlo', () => {
    render(<Harness />);
    expect(screen.getByRole('heading')).toHaveTextContent('Who has more engage?');
  });

  it('CA-506 — la definición se despliega al tocar el ícono de ayuda', () => {
    render(<Harness />);

    expect(screen.queryByText(HELP.text)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText(HELP.text)).toBeInTheDocument();
  });

  it('vuelve a cerrarse: no roba lugar a la tarjeta más de lo necesario', () => {
    render(<Harness />);
    const toggle = screen.getByRole('button');

    fireEvent.click(toggle);
    fireEvent.click(toggle);

    expect(screen.queryByText(HELP.text)).not.toBeInTheDocument();
  });

  it('sin definición no hay ícono que tocar', () => {
    render(
      <QuestionPrompt prompt="Who has more engage?" help={null} open={false} onToggle={() => {}} />,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
