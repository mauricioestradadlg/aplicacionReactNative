"""Cada venta conserva su importe completo y una única fecha de cobro."""
from datetime import date
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone


def completar_fechas_de_venta(apps, schema_editor):
    Cliente = apps.get_model('movil', 'Cliente')
    alias = schema_editor.connection.alias
    zona = ZoneInfo('America/Mexico_City')
    limite = timezone.localdate(timezone=zona)

    def valida(valor):
        return valor is not None and date(1900, 1, 1) <= valor <= limite

    for cliente in Cliente.objects.using(alias).filter(hubo_venta=True).iterator():
        if valida(cliente.fecha_venta):
            continue
        creado = cliente.creado_en
        fecha_creacion = timezone.localtime(creado, zona).date() if timezone.is_aware(creado) else creado.date()
        candidatas = (
            cliente.fecha_liquidacion if cliente.proyecto_liquidado else None,
            cliente.fecha_anticipo,
            fecha_creacion,
        )
        fecha_venta = next((valor for valor in candidatas if valida(valor)), None)
        Cliente.objects.using(alias).filter(pk=cliente.pk).update(fecha_venta=fecha_venta)


class Migration(migrations.Migration):
    dependencies = [('movil', '0001_initial')]

    operations = [
        migrations.RunPython(completar_fechas_de_venta, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='cliente', name='movil_anticipo_valido'),
        migrations.RemoveConstraint(model_name='cliente', name='movil_liquidacion_coherente'),
        migrations.RemoveField(model_name='cliente', name='importe_anticipo'),
        migrations.RemoveField(model_name='cliente', name='fecha_anticipo'),
        migrations.RemoveField(model_name='cliente', name='proyecto_liquidado'),
        migrations.RemoveField(model_name='cliente', name='fecha_liquidacion'),
    ]
